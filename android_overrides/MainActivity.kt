package com.usmlewise.usmlewise_christ

import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity

/**
 * Adds FLAG_SECURE to the app window.
 *
 * Two things follow from this flag, both of which matter for a device that
 * displays children's names, caregiver phone numbers and photographs of
 * medical records:
 *
 *  1. Screenshots and screen recording of this app are blocked, so participant
 *     data cannot be captured into the device gallery — a shared folder that
 *     syncs to personal cloud accounts and is outside the study's control.
 *  2. The recent-apps switcher shows a blank card instead of a live preview of
 *     the last screen, so an open participant record is not readable by anyone
 *     who picks the handset up and taps the overview button.
 *
 * Collectors work in homes and clinics with other people present, which makes
 * over-the-shoulder exposure a realistic threat rather than a theoretical one.
 *
 * Note: this is copied over the generated MainActivity.kt by the GitHub
 * Actions workflow. The package name must match the --org passed to
 * `flutter create` (com.usmlewise) plus the project name (usmlewise_christ).
 */
class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setFlags(
            WindowManager.LayoutParams.FLAG_SECURE,
            WindowManager.LayoutParams.FLAG_SECURE,
        )
    }
}
