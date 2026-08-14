from django.views.decorators.cache import never_cache
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse

from .models import RPAWorkflow, WorkflowRun, WorkflowStep

import time
import random
import csv
from io import BytesIO


# =========================================================
# RPA DASHBOARD
# =========================================================

@login_required
@never_cache
def dashboard(request):

    workflows = RPAWorkflow.objects.all()

    # -----------------------------------------------------
    # STATISTICS FOR EACH WORKFLOW
    # -----------------------------------------------------

    for workflow in workflows:

        workflow_runs = (
            WorkflowRun.objects
            .filter(workflow=workflow)
            .order_by("-started_at")
        )

        # Total Runs
        total_runs = workflow_runs.count()

        # Successful Runs
        success_runs = workflow_runs.filter(
            status="SUCCESS"
        ).count()

        workflow.total_runs = total_runs
        workflow.success_runs = success_runs

        # Pass Rate
        if total_runs > 0:
            workflow.pass_rate = round(
                (success_runs / total_runs) * 100,
                1
            )
        else:
            workflow.pass_rate = 0.0

        # Last Run
        workflow.last_run = workflow_runs.first()

        # Last Run Date
        if workflow.last_run:
            workflow.last_run_at = workflow.last_run.started_at
        else:
            workflow.last_run_at = None

        # Execution Progress
        if workflow.last_run:

            if workflow.last_run.status == "SUCCESS":
                workflow.execution_progress = 100

            elif workflow.last_run.status in ["FAILURE", "FAILED"]:
                workflow.execution_progress = 0

            else:
                workflow.execution_progress = (
                    getattr(
                        workflow.last_run,
                        "progress",
                        0
                    ) or 0
                )

        else:
            workflow.execution_progress = 0

    # -----------------------------------------------------
    # RECENT RUNS
    # -----------------------------------------------------

    recent_runs = (
        WorkflowRun.objects
        .select_related("workflow")
        .order_by("-started_at")[:5]
    )

    # -----------------------------------------------------
    # GLOBAL STATISTICS
    # -----------------------------------------------------

    total_runs = WorkflowRun.objects.count()

    success_runs = WorkflowRun.objects.filter(
        status="SUCCESS"
    ).count()

    if total_runs > 0:
        success_rate = round(
            (success_runs / total_runs) * 100,
            1
        )
    else:
        success_rate = 0.0

    # -----------------------------------------------------
    # CONTEXT
    # -----------------------------------------------------

    context = {
        "workflows": workflows,
        "recent_runs": recent_runs,
        "total_runs": total_runs,
        "success_runs": success_runs,
        "success_rate": success_rate,
    }

    return render(
        request,
        "rpa_dashboard/dashboard.html",
        context
    )


# =========================================================
# WORKFLOW DETAIL
# =========================================================

@login_required
@never_cache
def workflow_detail(request, wf_id):

    workflow = get_object_or_404(
        RPAWorkflow,
        wf_id=wf_id
    )

    # -----------------------------------------------------
    # ALL RUNS
    # -----------------------------------------------------

    all_runs = (
        WorkflowRun.objects
        .filter(workflow=workflow)
        .order_by("-started_at")
    )

    recent_runs = all_runs[:10]

    # -----------------------------------------------------
    # PASS RATE
    # -----------------------------------------------------

    total_runs = all_runs.count()

    success_runs = all_runs.filter(
        status="SUCCESS"
    ).count()

    if total_runs > 0:
        pass_rate = round(
            (success_runs / total_runs) * 100,
            1
        )
    else:
        pass_rate = 0.0

    # -----------------------------------------------------
    # AVERAGE DURATION
    # -----------------------------------------------------

    durations = [
        run.duration_ms
        for run in all_runs
        if getattr(run, "duration_ms", None) is not None
    ]

    if durations:
        avg_duration = round(
            sum(durations) / len(durations)
        )
    else:
        avg_duration = 0

    # -----------------------------------------------------
    # CURRENT / LAST RUN PROGRESS
    # -----------------------------------------------------

    last_run = all_runs.first()

    if last_run:

        if last_run.status == "SUCCESS":
            execution_progress = 100

        elif last_run.status in ["FAILURE", "FAILED"]:
            execution_progress = 0

        else:
            execution_progress = (
                getattr(last_run, "progress", 0) or 0
            )

    else:
        execution_progress = 0

    # -----------------------------------------------------
    # CONTEXT
    # -----------------------------------------------------

    context = {
        "workflow": workflow,
        "history": recent_runs,
        "recent_runs": recent_runs,
        "total_runs": total_runs,
        "success_runs": success_runs,
        "pass_rate": pass_rate,
        "avg_duration": avg_duration,
        "last_run": last_run,
        "execution_progress": execution_progress,
    }

    return render(
        request,
        "rpa_dashboard/workflow_detail.html",
        context
    )


# =========================================================
# START WORKFLOW
# =========================================================
#
# LOCAL DEVELOPMENT VERSION
#
# Celery / Redis are bypassed.
# Workflow executes directly.
#
# =========================================================

@login_required
@user_passes_test(lambda u: u.is_staff)
def start_workflow_run(request, wf_id):

    # -----------------------------------------------------
    # ONLY POST
    # -----------------------------------------------------

    if request.method != "POST":

        return JsonResponse(
            {
                "status": "invalid_method",
                "message": "POST request required."
            },
            status=405
        )

    # -----------------------------------------------------
    # GET WORKFLOW
    # -----------------------------------------------------

    workflow = get_object_or_404(
        RPAWorkflow,
        wf_id=wf_id
    )

    # -----------------------------------------------------
    # CREATE RUN
    # -----------------------------------------------------

    run = WorkflowRun.objects.create(
        workflow=workflow,
        status="PENDING",
        triggered_by=request.user,
        progress=0
    )

    # -----------------------------------------------------
    # CREATE STEPS
    # -----------------------------------------------------

    steps_data = []

    step_definitions = workflow.step_definitions or []

    for i, step_name in enumerate(step_definitions):

        step = WorkflowStep.objects.create(
            run=run,
            step_id=f"{i + 1:02d}",
            name=step_name,
            status="PENDING"
        )

        steps_data.append(
            {
                "id": step.id,
                "step_id": step.step_id,
                "name": step.name,
                "status": step.status,
            }
        )

    # -----------------------------------------------------
    # EXECUTE WORKFLOW DIRECTLY
    #
    # IMPORTANT:
    # NO .delay()
    # NO REDIS
    # NO CELERY BROKER
    # -----------------------------------------------------

    try:

        from .tasks import execute_workflow_task

        execute_workflow_task(run.id)

    except Exception as exc:

        run.status = "FAILURE"

        update_fields = [
            "status"
        ]

        if hasattr(run, "progress"):
            run.progress = 0
            update_fields.append(
                "progress"
            )

        run.save(
            update_fields=update_fields
        )

        return JsonResponse(
            {
                "status": "error",
                "run_id": run.id,
                "message": str(exc),
            },
            status=500
        )

    # -----------------------------------------------------
    # REFRESH RUN
    # -----------------------------------------------------

    run.refresh_from_db()

    # Safety:
    # if the task finished successfully but progress
    # was not changed to 100, correct it here.

    if run.status == "SUCCESS":

        current_progress = (
            getattr(run, "progress", 0) or 0
        )

        if current_progress != 100:

            run.progress = 100

            run.save(
                update_fields=["progress"]
            )

    # -----------------------------------------------------
    # REFRESH STEPS
    # -----------------------------------------------------

    refreshed_steps = []

    for step in run.steps.all():

        refreshed_steps.append(
            {
                "id": step.id,
                "step_id": step.step_id,
                "name": step.name,
                "status": step.status,
                "duration_ms": getattr(
                    step,
                    "duration_ms",
                    None
                ),
            }
        )

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    return JsonResponse(
        {
            "status": "success",
            "run_id": run.id,
            "run_status": run.status,
            "progress": getattr(
                run,
                "progress",
                0
            ),
            "message": "Workflow executed successfully.",
            "steps": refreshed_steps,
        }
    )


# =========================================================
# MANUAL STEP RUNNER
# =========================================================

@login_required
def run_step_api(request, step_id):

    if request.method != "POST":

        return JsonResponse(
            {
                "status": "error",
                "message": "Invalid method"
            },
            status=405
        )

    step = get_object_or_404(
        WorkflowStep,
        id=step_id
    )

    # -----------------------------------------------------
    # SIMULATE STEP
    # -----------------------------------------------------

    started = time.perf_counter()

    time.sleep(
        random.uniform(
            0.5,
            1.5
        )
    )

    step.status = (
        "PASS"
        if random.random() > 0.1
        else "FAIL"
    )

    # -----------------------------------------------------
    # DURATION
    # -----------------------------------------------------

    duration_ms = round(
        (time.perf_counter() - started) * 1000
    )

    update_fields = [
        "status"
    ]

    if hasattr(step, "duration_ms"):

        step.duration_ms = duration_ms

        update_fields.append(
            "duration_ms"
        )

    step.save(
        update_fields=update_fields
    )

    return JsonResponse(
        {
            "status": "success",
            "step_status": step.status,
            "duration_ms": duration_ms,
        }
    )


# =========================================================
# EXPORT CSV
# =========================================================

@login_required
def export_run_csv(request, run_id):

    run = get_object_or_404(
        WorkflowRun,
        id=run_id
    )

    # -----------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------

    response = HttpResponse(
        content_type="text/csv; charset=utf-8"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="run_{run.id}.csv"'
    )

    writer = csv.writer(
        response
    )

    # -----------------------------------------------------
    # HEADER
    # -----------------------------------------------------

    writer.writerow(
        [
            "RPA Workflow Execution Report"
        ]
    )

    writer.writerow([])

    writer.writerow(
        [
            "Run ID",
            run.id
        ]
    )

    writer.writerow(
        [
            "Workflow",
            str(run.workflow)
        ]
    )

    writer.writerow(
        [
            "Status",
            run.status
        ]
    )

    progress = (
        100
        if run.status == "SUCCESS"
        else (getattr(run, "progress", 0) or 0)
    )

    writer.writerow(
        [
            "Progress",
            f"{progress}%"
        ]
    )

    writer.writerow(
        [
            "Triggered By",
            (
                str(run.triggered_by)
                if run.triggered_by
                else "N/A"
            )
        ]
    )

    writer.writerow(
        [
            "Duration",
            (
                f"{run.duration_ms} ms"
                if getattr(
                    run,
                    "duration_ms",
                    None
                ) is not None
                else "N/A"
            )
        ]
    )

    writer.writerow([])

    # -----------------------------------------------------
    # STEPS HEADER
    # -----------------------------------------------------

    writer.writerow(
        [
            "Step ID",
            "Name",
            "Status",
            "Duration"
        ]
    )

    # -----------------------------------------------------
    # STEPS
    # -----------------------------------------------------

    for step in run.steps.all():

        duration = getattr(
            step,
            "duration_ms",
            None
        )

        writer.writerow(
            [
                step.step_id,
                step.name,
                step.status,
                (
                    f"{duration} ms"
                    if duration is not None
                    else "N/A"
                )
            ]
        )

    return response


# =========================================================
# EXPORT PDF
# =========================================================
#
# REPORTLAB VERSION
# WeasyPrint is NOT required.
#
# =========================================================

@login_required
def export_run_pdf(request, run_id):

    # -----------------------------------------------------
    # REPORTLAB IMPORTS
    # -----------------------------------------------------

    try:

        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors

        from reportlab.lib.styles import (
            getSampleStyleSheet,
            ParagraphStyle,
        )

        from reportlab.lib.enums import TA_CENTER

        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
        )

    except ImportError as exc:

        return HttpResponse(
            f"PDF generation not available: {exc}",
            status=501
        )

    # -----------------------------------------------------
    # GET RUN
    # -----------------------------------------------------

    run = get_object_or_404(
        WorkflowRun,
        id=run_id
    )

    # -----------------------------------------------------
    # BUFFER
    # -----------------------------------------------------

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
        title=f"RPA Run {run.id}",
        author="OnWebApp",
    )

    styles = getSampleStyleSheet()

    # -----------------------------------------------------
    # STYLES
    # -----------------------------------------------------

    title_style = ParagraphStyle(
        "OnWebAppTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=22,
        leading=27,
        spaceAfter=20,
        textColor=colors.HexColor(
            "#1F2937"
        ),
    )

    section_style = ParagraphStyle(
        "OnWebAppSection",
        parent=styles["Heading2"],
        fontSize=15,
        leading=19,
        spaceAfter=10,
        textColor=colors.HexColor(
            "#1F2937"
        ),
    )

    elements = []

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    elements.append(
        Paragraph(
            "RPA Workflow Execution Report",
            title_style
        )
    )

    elements.append(
        Spacer(
            1,
            10
        )
    )

    # -----------------------------------------------------
    # WORKFLOW INFORMATION
    # -----------------------------------------------------

    workflow_name = getattr(
        run.workflow,
        "name",
        None
    )

    if not workflow_name:
        workflow_name = str(
            run.workflow
        )

    triggered_by = (
        str(run.triggered_by)
        if run.triggered_by
        else "N/A"
    )

    # Correct SUCCESS progress
    if run.status == "SUCCESS":
        progress = 100
    else:
        progress = (
            getattr(
                run,
                "progress",
                0
            ) or 0
        )

    started_at = getattr(
        run,
        "started_at",
        None
    )

    started_at_text = (
        started_at.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        if started_at
        else "N/A"
    )

    duration_ms = getattr(
        run,
        "duration_ms",
        None
    )

    duration_text = (
        f"{duration_ms} ms"
        if duration_ms is not None
        else "N/A"
    )

    # -----------------------------------------------------
    # INFO TABLE
    # -----------------------------------------------------

    info_data = [
        [
            "Run ID",
            str(run.id)
        ],
        [
            "Workflow",
            workflow_name
        ],
        [
            "Status",
            str(run.status)
        ],
        [
            "Progress",
            f"{progress}%"
        ],
        [
            "Triggered By",
            triggered_by
        ],
        [
            "Started At",
            started_at_text
        ],
        [
            "Duration",
            duration_text
        ],
    ]

    info_table = Table(
        info_data,
        colWidths=[
            130,
            330
        ]
    )

    info_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#EAF2F8")
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#1F2937")
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (0, -1),
                    "Helvetica-Bold"
                ),
                (
                    "FONTNAME",
                    (1, 0),
                    (1, -1),
                    "Helvetica"
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#CBD5E1")
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE"
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    8
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    8
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    8
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    8
                ),
            ]
        )
    )

    elements.append(
        info_table
    )

    elements.append(
        Spacer(
            1,
            25
        )
    )

    # -----------------------------------------------------
    # STEPS TITLE
    # -----------------------------------------------------

    elements.append(
        Paragraph(
            "Workflow Steps",
            section_style
        )
    )

    elements.append(
        Spacer(
            1,
            10
        )
    )

    # -----------------------------------------------------
    # STEPS TABLE
    # -----------------------------------------------------

    step_data = [
        [
            "Step ID",
            "Name",
            "Status",
            "Duration"
        ]
    ]

    steps = run.steps.all()

    for step in steps:

        step_duration = getattr(
            step,
            "duration_ms",
            None
        )

        step_duration_text = (
            f"{step_duration} ms"
            if step_duration is not None
            else "N/A"
        )

        step_data.append(
            [
                str(step.step_id),
                str(step.name),
                str(step.status),
                step_duration_text,
            ]
        )

    if len(step_data) == 1:

        step_data.append(
            [
                "-",
                "No workflow steps found",
                "-",
                "-"
            ]
        )

    step_table = Table(
        step_data,
        colWidths=[
            70,
            220,
            90,
            80
        ],
        repeatRows=1
    )

    step_table.setStyle(
        TableStyle(
            [
                # HEADER
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#1F4E78")
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold"
                ),

                # BODY
                (
                    "FONTNAME",
                    (0, 1),
                    (-1, -1),
                    "Helvetica"
                ),
                (
                    "TEXTCOLOR",
                    (0, 1),
                    (-1, -1),
                    colors.HexColor("#1F2937")
                ),

                # GRID
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#CBD5E1")
                ),

                # ALIGNMENT
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE"
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (0, -1),
                    "CENTER"
                ),
                (
                    "ALIGN",
                    (2, 0),
                    (-1, -1),
                    "CENTER"
                ),

                # PADDING
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    7
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    7
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    8
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    8
                ),
            ]
        )
    )

    elements.append(
        step_table
    )

    elements.append(
        Spacer(
            1,
            25
        )
    )

    # -----------------------------------------------------
    # FOOTER
    # -----------------------------------------------------

    elements.append(
        Paragraph(
            "Generated by OnWebApp RPA Dashboard",
            styles["Normal"]
        )
    )

    # -----------------------------------------------------
    # BUILD PDF
    # -----------------------------------------------------

    try:

        doc.build(
            elements
        )

        pdf = buffer.getvalue()

    except Exception as exc:

        buffer.close()

        return HttpResponse(
            f"PDF generation failed: {exc}",
            status=500
        )

    buffer.close()

    # -----------------------------------------------------
    # RETURN PDF
    # -----------------------------------------------------

    response = HttpResponse(
        pdf,
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="rpa_run_{run.id}.pdf"'
    )

    return response