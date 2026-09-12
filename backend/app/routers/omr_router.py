"""OMR endpoints: upload scanned CRIST sheets, AI-extract them, review, export.

Admin-only. Uploaded PDFs are split into per-page JPEGs stored in MEDIA_DIR;
extraction runs in a background task against the AI endpoint configured in
Settings (see ai_client). Extracted data lives in the omr_* tables, separate
from app-collected `collections`, and only becomes "approved" after an admin
reviews the page side-by-side with the scan.
"""
import csv
import io
import os
from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query,
    Request, Response, UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import ai_client, audit, crypto, models, omr_normalize, schemas
from ..audit import Action
from ..auth import get_current_admin
from ..config import settings
from ..database import SessionLocal, get_db

router = APIRouter(prefix="/api", tags=["omr"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
# Long-edge cap for stored page images: phone photos can be 4000px+, which
# only wastes tokens. ~2300px keeps handwriting crisp for the model.
_MAX_IMAGE_EDGE = 2300
_PDF_RENDER_SCALE = 2.5  # A4 at 72pt base -> ~1490x2100 px


# ---------- helpers ----------

def _norm_answer(v: Optional[str]) -> Optional[str]:
    """Any spelling of a yes/no cell -> "yes" / "no" / None.

    Shared with the AI path so a reviewer typing "हाँ" or a tick into the
    review screen is stored the same way the model's answer would be.
    """
    return omr_normalize.normalize_answer(v)


def _save_jpeg(image, filename: str) -> None:
    """Downscale (if needed) and save a PIL image as JPEG in MEDIA_DIR.

    Scanned screening sheets carry handwritten names, mobile numbers and
    village names, so they are encrypted at rest exactly like the medical-record
    photographs: the JPEG is encoded in memory and written as ciphertext.
    """
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    w, h = image.size
    edge = max(w, h)
    if edge > _MAX_IMAGE_EDGE:
        ratio = _MAX_IMAGE_EDGE / edge
        image = image.resize((int(w * ratio), int(h * ratio)))
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=88)
    crypto.write_encrypted(
        os.path.join(settings.MEDIA_DIR, filename), buf.getvalue()
    )


def _pdf_to_page_images(pdf_bytes: bytes, batch_id: str) -> List[str]:
    """Render each PDF page to a JPEG in MEDIA_DIR; returns the filenames."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(pdf_bytes)
    filenames = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            bitmap = page.render(scale=_PDF_RENDER_SCALE)
            pil = bitmap.to_pil()
            name = f"omr_{batch_id}_p{i + 1}.jpg"
            _save_jpeg(pil, name)
            filenames.append(name)
            page.close()
    finally:
        doc.close()
    return filenames


def _image_to_page_image(raw: bytes, batch_id: str, index: int) -> str:
    from PIL import Image

    try:
        pil = Image.open(io.BytesIO(raw))
        pil.load()
    except Exception:
        raise HTTPException(400, "Could not read one of the uploaded images.")
    name = f"omr_{batch_id}_p{index}.jpg"
    _save_jpeg(pil, name)
    return name


def _remove_media(filename: Optional[str]) -> None:
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return
    path = os.path.join(settings.MEDIA_DIR, filename)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _apply_extraction(page: models.OmrPage, data, model_name: str) -> None:
    """Write one extraction result onto a page (replaces existing rows).

    `data` is whatever JSON the model returned. omr_normalize maps it onto our
    columns: it accepts the alternative key names and answer words models
    reach for, and converts any way of writing an age — including a date of
    birth, which it turns into years and months against the sheet's own date.
    """
    result = omr_normalize.normalize_extraction(data)
    header = result["header"]
    footer = result["footer"]
    page.kind = result["kind"]
    page.language_detected = result["language"]
    page.place = header["place"]
    page.block = header["block"]
    page.district = header["district"]
    page.sheet_date = header["date"]
    page.filler_name = footer["filler_name"]
    page.filler_designation = footer["designation"]
    page.filler_mobile = (footer["mobile"] or "")[:32] or None
    page.model_used = model_name[:128] or None
    page.rows.clear()
    for row in result["rows"]:
        page.rows.append(models.OmrRow(**row))
    page.status = "extracted"
    page.error = None
    page.extracted_at = datetime.utcnow()
    page.approved_at = None


def _row_birth_date(row: models.OmrRow):
    """The date of birth a row was written with, if its age cell was one."""
    return omr_normalize.parse_date(row.age_text)


def _link_batch_pages(db: Session, batch_id: str,
                      flag_missing: bool = True) -> None:
    """Join questionnaire pages onto the village list they belong to.

    Some uploads put a village roster on one page and then one full-page
    questionnaire per child after it, so a child's age and a child's answers
    arrive on different pages. This walks a finished batch and moves each
    questionnaire's four answers onto that child's roster row.

    A questionnaire is matched on the two things written across the top of it:
    the serial number (usually circled) and the date of birth. Where neither
    was readable, a lone remaining questionnaire is paired with a lone
    remaining child; anything still unmatched is left alone and flagged, never
    guessed, because attaching answers to the wrong child is worse than
    leaving a page for a human.
    """
    pages = db.query(models.OmrPage).filter(
        models.OmrPage.batch_id == batch_id
    ).order_by(models.OmrPage.page_number).all()
    questionnaires = [p for p in pages
                      if p.kind == omr_normalize.KIND_QUESTIONNAIRE and p.rows]
    roster_rows = [r for p in pages if p.kind == omr_normalize.KIND_ROSTER
                   for r in p.rows]
    if not questionnaires or not roster_rows:
        return

    taken = set()
    unmatched = []
    for page in questionnaires:
        answer_row = page.rows[0]
        serial = answer_row.serial or 0
        birth = _row_birth_date(answer_row)
        free = [r for r in roster_rows if id(r) not in taken]

        by_serial = [r for r in free if r.serial and r.serial == serial]
        by_birth = [r for r in free
                    if birth and _row_birth_date(r) == birth]

        target, confident = None, True
        if len(by_serial) == 1 and (not by_birth or by_serial[0] in by_birth):
            target = by_serial[0]
        elif len(by_birth) == 1:
            # Either no serial was written, or it points at a different child.
            # The date wins: three numbers agreeing exactly is far stronger
            # evidence than one digit, and a misread circled digit is the
            # commoner mistake. A disagreement is flagged, not hidden.
            target, confident = by_birth[0], not by_serial
        elif len(by_serial) == 1:
            # The date matched nobody, or matched several children. Fall back
            # to the written serial and flag the row.
            target, confident = by_serial[0], False

        if target is None:
            unmatched.append(page)
            continue
        _merge_answers(answer_row, target, confident)
        taken.add(id(target))

    # Last resort: exactly one child and exactly one questionnaire left over.
    leftover = [r for r in roster_rows if id(r) not in taken]
    if len(unmatched) == 1 and len(leftover) == 1:
        _merge_answers(unmatched[0].rows[0], leftover[0], True)
        taken.add(id(leftover[0]))
        unmatched = []

    for page in unmatched:
        page.rows[0].uncertain = True
    # A child with no questionnaire in the batch is a page that never arrived.
    # Skipped when re-linking after an edit, so that a flag a reviewer has
    # already cleared does not come straight back.
    if flag_missing:
        for row in roster_rows:
            if id(row) not in taken:
                row.uncertain = True


def _merge_answers(source: models.OmrRow, target: models.OmrRow,
                   confident: bool) -> None:
    """Move a questionnaire's answers onto the child's roster row.

    The questionnaire row is then removed: its answers now live on the roster
    row, and keeping a second copy would double-count the child in exports.
    The scanned page stays, so the merge is still checkable against the image.
    """
    target.q1, target.q2, target.q3, target.q4 = (
        source.q1, source.q2, source.q3, source.q4
    )
    if source.uncertain or not confident:
        target.uncertain = True
    if source.page is not None:
        source.page.rows.remove(source)


def _process_pages(page_ids: List[str]) -> None:
    """Background task: extract each page with the configured AI model.

    Runs pages sequentially (one API call at a time) with its own DB session —
    the request-scoped session is long gone by the time this runs.
    """
    db = SessionLocal()
    batch_ids = set()
    try:
        cfg = ai_client.get_ai_config(db)
        for page_id in page_ids:
            page = db.query(models.OmrPage).filter(
                models.OmrPage.id == page_id
            ).first()
            if page is None or page.status not in ("pending", "processing"):
                continue
            page.status = "processing"
            db.commit()
            try:
                path = os.path.join(settings.MEDIA_DIR, page.image_filename)
                image_bytes = crypto.read_decrypted(path)
                language = page.batch.language if page.batch else "auto"

                # Sending a sheet to the vision model is a DISCLOSURE of PHI to
                # an external processor. It is recorded before the call so the
                # trail exists even if the request fails or the process dies —
                # and so the set of sheets that ever left the perimeter can be
                # reconstructed if the provider suffers a breach.
                audit.record(
                    actor_id=page.batch.uploaded_by if page.batch else None,
                    actor_name="system (background extraction)",
                    actor_role="admin",
                    action=Action.AI_DISCLOSURE,
                    resource_type="omr_page", resource_id=page.id,
                    subject_count=1,
                    detail=f"sheet image sent to {cfg.get('base_url') or 'unset'} "
                           f"model={cfg.get('model') or 'unset'}",
                )

                data = ai_client.extract_page(cfg, image_bytes, language)
                _apply_extraction(page, data, cfg.get("model") or "")
                batch_ids.add(page.batch_id)
            except Exception as e:  # noqa: BLE001 — any failure marks the page
                db.rollback()
                page = db.query(models.OmrPage).filter(
                    models.OmrPage.id == page_id
                ).first()
                if page is not None:
                    page.status = "failed"
                    page.error = str(e)[:2000]
            db.commit()

        # Only now, with every page of the batch read, can a questionnaire
        # page be matched to the child it belongs to.
        for batch_id in batch_ids:
            try:
                _link_batch_pages(db, batch_id)
                db.commit()
            except Exception:  # noqa: BLE001 — linking must not lose pages
                db.rollback()
    finally:
        db.close()


def _batch_or_404(db: Session, batch_id: str) -> models.OmrBatch:
    batch = db.query(models.OmrBatch).filter(
        models.OmrBatch.id == batch_id
    ).first()
    if batch is None:
        raise HTTPException(404, "Batch not found.")
    return batch


def _page_or_404(db: Session, page_id: str) -> models.OmrPage:
    page = db.query(models.OmrPage).filter(
        models.OmrPage.id == page_id
    ).first()
    if page is None:
        raise HTTPException(404, "Page not found.")
    return page


def _batch_out(batch: models.OmrBatch) -> schemas.OmrBatchOut:
    counts = {"pending": 0, "processing": 0, "extracted": 0,
              "approved": 0, "failed": 0}
    rows_count = 0
    for p in batch.pages:
        counts[p.status] = counts.get(p.status, 0) + 1
        rows_count += len(p.rows)
    return schemas.OmrBatchOut(
        id=batch.id,
        filename=batch.filename,
        name=batch.name,
        language=batch.language,
        created_at=batch.created_at,
        pages_total=len(batch.pages),
        pages_pending=counts["pending"] + counts["processing"],
        pages_extracted=counts["extracted"],
        pages_approved=counts["approved"],
        pages_failed=counts["failed"],
        rows_count=rows_count,
    )


def _page_summary(p: models.OmrPage) -> schemas.OmrPageSummary:
    return schemas.OmrPageSummary(
        id=p.id,
        page_number=p.page_number,
        status=p.status,
        kind=p.kind,
        error=p.error,
        rows_count=len(p.rows),
        uncertain_count=sum(1 for r in p.rows if r.uncertain),
    )


def _page_detail(p: models.OmrPage) -> schemas.OmrPageDetail:
    return schemas.OmrPageDetail(
        id=p.id,
        batch_id=p.batch_id,
        page_number=p.page_number,
        status=p.status,
        kind=p.kind,
        error=p.error,
        model_used=p.model_used,
        language_detected=p.language_detected,
        place=p.place,
        block=p.block,
        district=p.district,
        sheet_date=p.sheet_date,
        filler_name=p.filler_name,
        filler_designation=p.filler_designation,
        filler_mobile=p.filler_mobile,
        extracted_at=p.extracted_at,
        approved_at=p.approved_at,
        rows=[
            schemas.OmrRowIO(
                serial=r.serial,
                age_text=r.age_text,
                age_years=r.age_years,
                age_months=r.age_months,
                q1=r.q1, q2=r.q2, q3=r.q3, q4=r.q4,
                mobile=r.mobile,
                uncertain=r.uncertain,
            )
            for r in p.rows
        ],
    )


# ---------- AI settings ----------

@router.get("/ai/config", response_model=schemas.AiConfigOut)
def get_ai_config(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    cfg = ai_client.get_ai_config(db)
    return schemas.AiConfigOut(
        base_url=cfg["base_url"],
        model=cfg["model"],
        has_api_key=bool(cfg["api_key"]),
    )


@router.put("/ai/config", response_model=schemas.AiConfigOut)
def update_ai_config(
    body: schemas.AiConfigIn,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    ai_client.set_ai_config(db, body.base_url, body.api_key, body.model)
    cfg = ai_client.get_ai_config(db)
    return schemas.AiConfigOut(
        base_url=cfg["base_url"],
        model=cfg["model"],
        has_api_key=bool(cfg["api_key"]),
    )


@router.get("/ai/models", response_model=List[str])
def list_ai_models(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    cfg = ai_client.get_ai_config(db)
    try:
        return ai_client.list_models(cfg)
    except (ai_client.AiConfigError, ai_client.AiRequestError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # network errors etc.
        raise HTTPException(502, f"Could not reach the AI endpoint: {e}")


@router.post("/ai/test")
def test_ai(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    cfg = ai_client.get_ai_config(db)
    try:
        reply = ai_client.test_connection(cfg)
    except (ai_client.AiConfigError, ai_client.AiRequestError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Could not reach the AI endpoint: {e}")
    return {"ok": True, "reply": reply, "model": cfg["model"]}


# ---------- batches ----------

@router.post("/omr/upload", response_model=schemas.OmrBatchDetail, status_code=201)
def upload_batch(
    background: BackgroundTasks,
    files: List[UploadFile] = File(...),
    language: str = Form("auto"),
    name: str = Form(""),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Upload one PDF (each page becomes a sheet) and/or sheet photos.

    ``name`` is an optional label so the admin can tell what the batch was
    extracted from; it falls back to the filename when blank.
    """
    if language not in ("auto", "hi", "kn", "en"):
        language = "auto"
    # Fail early with a clear message instead of a burst of failed pages.
    cfg = ai_client.get_ai_config(db)
    if not (cfg["base_url"] and cfg["api_key"] and cfg["model"]):
        raise HTTPException(
            400,
            "Configure the AI integration first (Settings → AI Integration).",
        )

    batch = models.OmrBatch(
        filename=files[0].filename or "upload",
        name=(name or "").strip()[:255] or None,
        language=language,
        uploaded_by=admin.id,
    )
    db.add(batch)
    db.flush()  # batch.id for filenames

    page_no = 0
    for f in files:
        raw = f.file.read()
        if not raw:
            continue
        is_pdf = (
            (f.content_type or "").lower() == "application/pdf"
            or (f.filename or "").lower().endswith(".pdf")
            or raw[:5] == b"%PDF-"
        )
        if is_pdf:
            try:
                names = _pdf_to_page_images(raw, batch.id)
            except HTTPException:
                raise
            except Exception as e:
                db.rollback()
                raise HTTPException(400, f"Could not read the PDF: {e}")
        elif (f.content_type or "").lower() in _ALLOWED_IMAGE_TYPES or True:
            # Anything non-PDF is treated as an image; Pillow validates it.
            names = [_image_to_page_image(raw, batch.id, page_no + 1)]
        for name in names:
            page_no += 1
            db.add(models.OmrPage(
                batch_id=batch.id,
                page_number=page_no,
                image_filename=name,
                status="pending",
            ))

    if page_no == 0:
        db.rollback()
        raise HTTPException(400, "No readable pages found in the upload.")

    db.commit()
    db.refresh(batch)
    background.add_task(_process_pages, [p.id for p in batch.pages])
    out = _batch_out(batch)
    return schemas.OmrBatchDetail(
        **out.model_dump(), pages=[_page_summary(p) for p in batch.pages]
    )


@router.get("/omr/batches", response_model=List[schemas.OmrBatchOut])
def list_batches(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    batches = db.query(models.OmrBatch).order_by(
        models.OmrBatch.created_at.desc()
    ).all()
    return [_batch_out(b) for b in batches]


@router.get("/omr/batches/{batch_id}", response_model=schemas.OmrBatchDetail)
def batch_detail(
    batch_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    batch = _batch_or_404(db, batch_id)
    out = _batch_out(batch)
    return schemas.OmrBatchDetail(
        **out.model_dump(), pages=[_page_summary(p) for p in batch.pages]
    )


@router.patch("/omr/batches/{batch_id}", response_model=schemas.OmrBatchOut)
def rename_batch(
    batch_id: str,
    body: schemas.OmrBatchRename,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Set/clear the batch's label. Works even while pages are still
    extracting — it only touches the batch row, not the pages."""
    batch = _batch_or_404(db, batch_id)
    batch.name = (body.name or "").strip()[:255] or None
    db.commit()
    db.refresh(batch)
    return _batch_out(batch)


@router.delete("/omr/batches/{batch_id}", status_code=204)
def delete_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    batch = _batch_or_404(db, batch_id)
    image_names = [p.image_filename for p in batch.pages]
    db.delete(batch)  # pages + rows removed via cascade
    db.commit()
    for name in image_names:
        _remove_media(name)


# ---------- pages ----------

@router.get("/omr/pages/{page_id}", response_model=schemas.OmrPageDetail)
def page_detail(
    page_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    return _page_detail(_page_or_404(db, page_id))


@router.get("/omr/pages/{page_id}/image")
def page_image(
    page_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Serve a scanned sheet image, decrypted in memory and audited.

    A sheet holds up to 22 handwritten rows, so one view can expose many
    individuals at once — the audit row records that rather than counting it
    as a single access.
    """
    page = _page_or_404(db, page_id)
    path = os.path.join(settings.MEDIA_DIR, page.image_filename)
    if not os.path.isfile(path):
        raise HTTPException(404, "Page image not found.")

    try:
        content = crypto.read_decrypted(path)
    except crypto.MediaCryptoError as exc:
        audit.record_user(
            admin, Action.VIEW_OMR, request=request, success=False,
            resource_type="omr_page", resource_id=page.id, detail=str(exc)[:512],
        )
        raise HTTPException(500, "This sheet image could not be decrypted.")

    audit.record_user(
        admin, Action.VIEW_OMR, request=request,
        resource_type="omr_page", resource_id=page.id,
        subject_count=max(1, len(page.rows or [])),
    )
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, private"},
    )


@router.put("/omr/pages/{page_id}", response_model=schemas.OmrPageDetail)
def update_page(
    page_id: str,
    body: schemas.OmrPageUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Save review edits. Rows replace the existing set; editing un-approves."""
    page = _page_or_404(db, page_id)
    page.place = (body.place or "").strip()[:255] or None
    page.block = (body.block or "").strip()[:255] or None
    page.district = (body.district or "").strip()[:255] or None
    page.sheet_date = (body.sheet_date or "").strip()[:64] or None
    page.filler_name = (body.filler_name or "").strip()[:255] or None
    page.filler_designation = (body.filler_designation or "").strip()[:255] or None
    page.filler_mobile = (body.filler_mobile or "").strip()[:32] or None
    # A reviewer correcting the age cell may type a date of birth, "3 माह" or
    # "2½" — the same forms the sheets use. Fill the year/month columns from
    # it when they were left empty, counting against the sheet's own date.
    reference = omr_normalize.parse_date(page.sheet_date) or datetime.utcnow().date()
    page.rows.clear()
    for r in body.rows:
        age_text = (r.age_text or "").strip()[:64] or None
        years, months = r.age_years, r.age_months
        if years is None and months is None and age_text:
            parsed = omr_normalize.parse_age(age_text, reference)
            years, months = parsed["years"], parsed["months"]
        page.rows.append(models.OmrRow(
            serial=r.serial,
            age_text=age_text,
            age_years=years,
            age_months=months,
            q1=_norm_answer(r.q1),
            q2=_norm_answer(r.q2),
            q3=_norm_answer(r.q3),
            q4=_norm_answer(r.q4),
            mobile=omr_normalize.normalize_mobile(r.mobile)[0],
            uncertain=r.uncertain,
        ))
    if page.status in ("extracted", "approved"):
        page.status = "extracted"
        page.approved_at = None
    db.commit()

    # Correcting the serial or the date of birth on a questionnaire that could
    # not be matched is exactly how a reviewer fixes a failed link, so try the
    # match again with what they just typed.
    if page.kind == omr_normalize.KIND_QUESTIONNAIRE and page.rows:
        _link_batch_pages(db, page.batch_id, flag_missing=False)
        db.commit()

    db.refresh(page)
    return _page_detail(page)


@router.post("/omr/pages/{page_id}/approve", response_model=schemas.OmrPageDetail)
def approve_page(
    page_id: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    page = _page_or_404(db, page_id)
    if page.status not in ("extracted", "approved"):
        raise HTTPException(400, "Page has no extracted data to approve yet.")
    page.status = "approved"
    page.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(page)
    return _page_detail(page)


@router.post("/omr/pages/{page_id}/rerun", response_model=schemas.OmrPageSummary)
def rerun_page(
    page_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """Re-run AI extraction on one page (overwrites its rows).

    Re-reading a village list also re-reads that batch's questionnaire pages.
    Their answers were moved onto the list's rows and the questionnaire rows
    removed, so a list read on its own would come back with no answers at all.
    """
    page = _page_or_404(db, page_id)
    pages = [page]
    if page.kind == omr_normalize.KIND_ROSTER:
        pages += [
            p for p in (page.batch.pages if page.batch else [])
            if p.kind == omr_normalize.KIND_QUESTIONNAIRE
        ]
    for p in pages:
        p.status = "pending"
        p.error = None
    db.commit()
    background.add_task(_process_pages, [p.id for p in pages])
    return _page_summary(page)


# ---------- export ----------

@router.get("/omr/export.csv")
def export_omr_csv(
    batch_id: Optional[str] = None,
    approved_only: bool = Query(True),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """All extracted rows as CSV (default: approved pages only)."""
    q = db.query(models.OmrPage).join(models.OmrBatch)
    if batch_id:
        q = q.filter(models.OmrPage.batch_id == batch_id)
    if approved_only:
        q = q.filter(models.OmrPage.status == "approved")
    else:
        q = q.filter(models.OmrPage.status.in_(["extracted", "approved"]))
    pages = q.order_by(
        models.OmrBatch.created_at.desc(), models.OmrPage.page_number
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "batch_name", "batch_file", "page", "page_status",
        "place", "block", "district",
        "sheet_date", "serial", "age_text", "age_years", "age_months",
        "q1", "q2", "q3", "q4", "mobile", "uncertain",
        "filler_name", "filler_designation", "filler_mobile", "language",
    ])
    for p in pages:
        for r in p.rows:
            writer.writerow([
                (p.batch.name or p.batch.filename) if p.batch else "",
                p.batch.filename if p.batch else "",
                p.page_number,
                p.status,
                p.place or "", p.block or "", p.district or "",
                p.sheet_date or "",
                r.serial,
                r.age_text or "",
                r.age_years if r.age_years is not None else "",
                r.age_months if r.age_months is not None else "",
                r.q1 or "", r.q2 or "", r.q3 or "", r.q4 or "",
                r.mobile or "",
                "yes" if r.uncertain else "no",
                p.filler_name or "", p.filler_designation or "",
                p.filler_mobile or "",
                p.language_detected or "",
            ])
    buf.seek(0)
    filename = f"omr_data_{datetime.utcnow():%Y%m%d}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
