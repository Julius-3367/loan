#!/usr/bin/env python3
"""
fix_stepper.py
Surgically replaces the broken APPLICATION STATUS TIMELINE STEPPER block
in templates/loans/application_detail.html with a clean, correctly-structured
version that uses only direct application.status string comparisons (no
{% with %} numeric variables, which Django templates do not support via
{% elif %} branching).

Run from loan_system/:
    python fix_stepper.py
"""

import os
import sys

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "templates", "loans", "application_detail.html"
)

START_MARKER = "        <!-- =====================================================================\n             APPLICATION STATUS TIMELINE STEPPER"
END_MARKER = "        </div><!-- /stepper card -->"

# ---------------------------------------------------------------------------
# The replacement block — pure, formatter-safe HTML + Django template tags.
# Each circle div is written on separate lines so nothing gets mangled.
# ---------------------------------------------------------------------------
STEPPER = """\
        <!-- ================================================================
             APPLICATION STATUS TIMELINE STEPPER
             Stage order:
               0 DRAFT - 1 SUBMITTED - 2 UNDER_REVIEW - 3 CREDIT_ANALYSIS
               4 PENDING_APPROVAL - 5 APPROVED - 6 EMPLOYER_VERIFICATION
               7 GUARANTOR_CONFIRMATION - 8 DISBURSED
             Terminal states: REJECTED, CANCELLED
             All stage tests use direct application.status string comparisons.
             No {% with %} numeric index variables are used.
        ================================================================ -->

        <div class="mb-8 bg-white shadow-sm rounded-lg border border-gray-200 overflow-hidden">

            <!-- Header bar -->
            <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                <h3 class="text-sm font-semibold text-gray-700 uppercase tracking-wide">Application Progress</h3>
                <span class="text-xs text-gray-500">
                    {% if application.status == 'REJECTED' %}Application Rejected
                    {% elif application.status == 'CANCELLED' %}Application Cancelled
                    {% elif application.status == 'DISBURSED' %}Loan Disbursed &#8212; Complete
                    {% else %}Step
                        {% if application.status == 'DRAFT' %}1
                        {% elif application.status == 'SUBMITTED' %}2
                        {% elif application.status == 'UNDER_REVIEW' %}3
                        {% elif application.status == 'CREDIT_ANALYSIS' %}4
                        {% elif application.status == 'PENDING_APPROVAL' %}5
                        {% elif application.status == 'APPROVED' %}6
                        {% elif application.status == 'EMPLOYER_VERIFICATION' %}7
                        {% elif application.status == 'GUARANTOR_CONFIRMATION' %}8
                        {% endif %} of 9
                    {% endif %}
                </span>
            </div><!-- /header bar -->

            <div class="px-4 py-6 sm:px-6">

                <!-- ============================================================
                     DESKTOP STEPPER  (md and above - horizontal row)
                     Each step column: invisible-spacer | circle | connector
                     Left spacer on step 1 and right spacer on step 9 are
                     "invisible" so the row stays balanced.
                ============================================================ -->
                <div class="hidden md:flex items-start">

                    <!-- ── Step 1: DRAFT ─────────────────────────────────────
                         CURRENT  : DRAFT
                         COMPLETED: every other status (always behind DRAFT)
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            <div class="flex-1 h-0.5 invisible"></div>
                            {% if application.status == 'DRAFT' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-orange-500 ring-2 ring-orange-200 shadow-sm flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% endif %}
                            {% if application.status == 'DRAFT' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% endif %}
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'DRAFT' %}text-orange-600{% else %}text-green-700{% endif %}">Draft</p>
                        </div>
                    </div>

                    <!-- ── Step 2: SUBMITTED ─────────────────────────────────
                         FUTURE   : DRAFT
                         CURRENT  : SUBMITTED
                         COMPLETED: UNDER_REVIEW CREDIT_ANALYSIS PENDING_APPROVAL
                                    APPROVED EMPLOYER_VERIFICATION
                                    GUARANTOR_CONFIRMATION DISBURSED
                                    REJECTED CANCELLED
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            {% if application.status == 'DRAFT' %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% endif %}
                            {% if application.status == 'SUBMITTED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-orange-500 ring-2 ring-orange-200 shadow-sm flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                            </div>
                            {% elif application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center"></div>
                            {% endif %}
                            {% if application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'SUBMITTED' %}text-orange-600{% elif application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Submitted</p>
                        </div>
                    </div>

                    <!-- ── Step 3: UNDER_REVIEW ──────────────────────────────
                         FUTURE   : DRAFT SUBMITTED
                         CURRENT  : UNDER_REVIEW
                         COMPLETED: CREDIT_ANALYSIS PENDING_APPROVAL APPROVED
                                    EMPLOYER_VERIFICATION GUARANTOR_CONFIRMATION
                                    DISBURSED REJECTED CANCELLED
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            {% if application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                            {% if application.status == 'UNDER_REVIEW' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-orange-500 ring-2 ring-orange-200 shadow-sm flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                            </div>
                            {% elif application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center"></div>
                            {% endif %}
                            {% if application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'UNDER_REVIEW' %}text-orange-600{% elif application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Under Review</p>
                        </div>
                    </div>

                    <!-- ── Step 4: CREDIT_ANALYSIS ───────────────────────────
                         CURRENT  : CREDIT_ANALYSIS
                         COMPLETED: PENDING_APPROVAL APPROVED
                                    EMPLOYER_VERIFICATION GUARANTOR_CONFIRMATION
                                    DISBURSED REJECTED CANCELLED
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            {% if application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                            {% if application.status == 'CREDIT_ANALYSIS' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-orange-500 ring-2 ring-orange-200 shadow-sm flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                            </div>
                            {% elif application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center"></div>
                            {% endif %}
                            {% if application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'CREDIT_ANALYSIS' %}text-orange-600{% elif application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Credit Analysis</p>
                        </div>
                    </div>

                    <!-- ── Step 5: PENDING_APPROVAL ──────────────────────────
                         CURRENT  : PENDING_APPROVAL
                         COMPLETED: APPROVED EMPLOYER_VERIFICATION
                                    GUARANTOR_CONFIRMATION DISBURSED
                                    REJECTED CANCELLED
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            {% if application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                            {% if application.status == 'PENDING_APPROVAL' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-orange-500 ring-2 ring-orange-200 shadow-sm flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                            </div>
                            {% elif application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center"></div>
                            {% endif %}
                            {% if application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'PENDING_APPROVAL' %}text-orange-600{% elif application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Pend. Approval</p>
                        </div>
                    </div>

                    <!-- ── Step 6: APPROVED ──────────────────────────────────
                         CURRENT  : APPROVED
                         COMPLETED: EMPLOYER_VERIFICATION GUARANTOR_CONFIRMATION
                                    DISBURSED REJECTED CANCELLED
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            {% if application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                            {% if application.status == 'APPROVED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-orange-500 ring-2 ring-orange-200 shadow-sm flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                            </div>
                            {% elif application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center"></div>
                            {% endif %}
                            {% if application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'APPROVED' %}text-orange-600{% elif application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Approved</p>
                        </div>
                    </div>

                    <!-- ── Step 7: EMPLOYER_VERIFICATION ─────────────────────
                         CURRENT  : EMPLOYER_VERIFICATION
                         COMPLETED: GUARANTOR_CONFIRMATION DISBURSED
                                    REJECTED CANCELLED
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            {% if application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                            {% if application.status == 'EMPLOYER_VERIFICATION' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-orange-500 ring-2 ring-orange-200 shadow-sm flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                            </div>
                            {% elif application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center"></div>
                            {% endif %}
                            {% if application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'EMPLOYER_VERIFICATION' %}text-orange-600{% elif application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Employer Verif.</p>
                        </div>
                    </div>

                    <!-- ── Step 8: GUARANTOR_CONFIRMATION ────────────────────
                         CURRENT  : GUARANTOR_CONFIRMATION
                         COMPLETED: DISBURSED REJECTED CANCELLED
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            {% if application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                            {% if application.status == 'GUARANTOR_CONFIRMATION' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-orange-500 ring-2 ring-orange-200 shadow-sm flex items-center justify-center">
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                            </div>
                            {% elif application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center"></div>
                            {% endif %}
                            {% if application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'GUARANTOR_CONFIRMATION' %}text-orange-600{% elif application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Guarantor Conf.</p>
                        </div>
                    </div>

                    <!-- ── Step 9: DISBURSED ─────────────────────────────────
                         CURRENT/COMPLETED: DISBURSED
                         FUTURE: everything else
                    ──────────────────────────────────────────────────────── -->
                    <div class="flex flex-col items-center flex-1 min-w-0">
                        <div class="flex items-center w-full">
                            {% if application.status == 'DISBURSED' %}
                            <div class="flex-1 h-0.5 bg-green-400"></div>
                            {% else %}
                            <div class="flex-1 h-0.5 bg-gray-200"></div>
                            {% endif %}
                            {% if application.status == 'DISBURSED' %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-green-500 ring-2 ring-white shadow-sm flex items-center justify-center">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                            </div>
                            {% else %}
                            <div class="relative z-10 flex-shrink-0 w-8 h-8 rounded-full bg-white border-2 border-gray-300 flex items-center justify-center"></div>
                            {% endif %}
                            <div class="flex-1 h-0.5 invisible"></div>
                        </div>
                        <div class="mt-2 text-center px-1">
                            <p class="text-xs font-medium leading-tight {% if application.status == 'DISBURSED' %}text-green-700{% else %}text-gray-400{% endif %}">Disbursed</p>
                        </div>
                    </div>

                </div><!-- /desktop stepper flex row -->

                <!-- REJECTED / CANCELLED terminal banner (desktop only) -->
                {% if application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                <div class="hidden md:flex mt-5 items-center space-x-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                    <div class="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-red-500">
                        <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>
                    </div>
                    <div>
                        <p class="text-sm font-semibold text-red-700">Application {{ application.get_status_display }}</p>
                        {% if application.rejection_reason %}
                        <p class="text-xs text-red-600 mt-0.5">{{ application.rejection_reason }}</p>
                        {% endif %}
                    </div>
                </div>
                {% endif %}

                <!-- ============================================================
                     MOBILE STEPPER  (below md - vertical left-border timeline)
                ============================================================ -->
                <div class="md:hidden">
                    <ol class="relative border-l-2 border-gray-200 ml-3">

                        <!-- Step 1: DRAFT -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'DRAFT' %}bg-orange-500{% elif application.status == 'SUBMITTED' or application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'DRAFT' %}
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                                {% elif application.status == 'SUBMITTED' or application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'DRAFT' %}text-orange-600{% elif application.status == 'SUBMITTED' or application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Draft</h4>
                            </div>
                        </li>

                        <!-- Step 2: SUBMITTED -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'SUBMITTED' %}bg-orange-500{% elif application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'SUBMITTED' %}
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                                {% elif application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'SUBMITTED' %}text-orange-600{% elif application.status == 'UNDER_REVIEW' or application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Submitted</h4>
                            </div>
                        </li>

                        <!-- Step 3: UNDER_REVIEW -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'UNDER_REVIEW' %}bg-orange-500{% elif application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'UNDER_REVIEW' %}
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                                {% elif application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'UNDER_REVIEW' %}text-orange-600{% elif application.status == 'CREDIT_ANALYSIS' or application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Under Review</h4>
                            </div>
                        </li>

                        <!-- Step 4: CREDIT_ANALYSIS -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'CREDIT_ANALYSIS' %}bg-orange-500{% elif application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'CREDIT_ANALYSIS' %}
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                                {% elif application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'CREDIT_ANALYSIS' %}text-orange-600{% elif application.status == 'PENDING_APPROVAL' or application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Credit Analysis</h4>
                            </div>
                        </li>

                        <!-- Step 5: PENDING_APPROVAL -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'PENDING_APPROVAL' %}bg-orange-500{% elif application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'PENDING_APPROVAL' %}
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                                {% elif application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'PENDING_APPROVAL' %}text-orange-600{% elif application.status == 'APPROVED' or application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Pending Approval</h4>
                            </div>
                        </li>

                        <!-- Step 6: APPROVED -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'APPROVED' %}bg-orange-500{% elif application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'APPROVED' %}
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                                {% elif application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'APPROVED' %}text-orange-600{% elif application.status == 'EMPLOYER_VERIFICATION' or application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Approved</h4>
                            </div>
                        </li>

                        <!-- Step 7: EMPLOYER_VERIFICATION -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'EMPLOYER_VERIFICATION' %}bg-orange-500{% elif application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'EMPLOYER_VERIFICATION' %}
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                                {% elif application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'EMPLOYER_VERIFICATION' %}text-orange-600{% elif application.status == 'GUARANTOR_CONFIRMATION' or application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Employer Verification</h4>
                            </div>
                        </li>

                        <!-- Step 8: GUARANTOR_CONFIRMATION -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'GUARANTOR_CONFIRMATION' %}bg-orange-500{% elif application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'GUARANTOR_CONFIRMATION' %}
                                <div class="w-2.5 h-2.5 rounded-full bg-white"></div>
                                {% elif application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'GUARANTOR_CONFIRMATION' %}text-orange-600{% elif application.status == 'DISBURSED' or application.status == 'REJECTED' or application.status == 'CANCELLED' %}text-green-700{% else %}text-gray-400{% endif %}">Guarantor Confirmation</h4>
                            </div>
                        </li>

                        <!-- Step 9: DISBURSED -->
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full ring-4 ring-white {% if application.status == 'DISBURSED' %}bg-green-500{% else %}bg-white border-2 border-gray-300{% endif %}">
                                {% if application.status == 'DISBURSED' %}
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"/></svg>
                                {% endif %}
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-medium {% if application.status == 'DISBURSED' %}text-green-700{% else %}text-gray-400{% endif %}">Disbursed</h4>
                            </div>
                        </li>

                        <!-- REJECTED / CANCELLED terminal indicator (appended after step 9) -->
                        {% if application.status == 'REJECTED' or application.status == 'CANCELLED' %}
                        <li class="mb-0 ml-7">
                            <span class="absolute -left-4 flex items-center justify-center w-8 h-8 rounded-full bg-red-500 ring-4 ring-white">
                                <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>
                            </span>
                            <div class="py-3">
                                <h4 class="text-sm font-semibold text-red-600">{{ application.get_status_display }}</h4>
                                {% if application.rejection_reason %}
                                <p class="text-xs text-red-500 mt-0.5">{{ application.rejection_reason }}</p>
                                {% endif %}
                            </div>
                        </li>
                        {% endif %}

                    </ol>
                </div><!-- /mobile stepper -->

            </div><!-- /inner padding -->
        </div><!-- /stepper card -->"""


def main() -> None:
    if not os.path.exists(TEMPLATE_PATH):
        print(f"ERROR: template not found at {TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as fh:
        content = fh.read()

    start_idx = content.find(START_MARKER)
    end_idx = content.find(END_MARKER)

    if start_idx == -1:
        print(f"ERROR: start marker not found:\n  {START_MARKER!r}", file=sys.stderr)
        sys.exit(1)
    if end_idx == -1:
        print(f"ERROR: end marker not found:\n  {END_MARKER!r}", file=sys.stderr)
        sys.exit(1)

    end_idx += len(END_MARKER)

    print(
        f"Found stepper block: chars {start_idx}..{end_idx}  "
        f"({end_idx - start_idx} chars)"
    )

    new_content = content[:start_idx] + STEPPER + "\n\n" + content[end_idx:]

    # Quick sanity check: the result must still contain the grid div
    if 'class="grid grid-cols-1 lg:grid-cols-3 gap-8"' not in new_content:
        print("ERROR: grid div missing from output — aborting", file=sys.stderr)
        sys.exit(1)

    # Write a backup first
    backup_path = TEMPLATE_PATH + ".bak"
    with open(backup_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"Backup written to {backup_path}")

    with open(TEMPLATE_PATH, "w", encoding="utf-8") as fh:
        fh.write(new_content)

    line_count = new_content.count("\n") + 1
    print(f"Done. New file: {line_count} lines  ({TEMPLATE_PATH})")


if __name__ == "__main__":
    main()
