from django.urls import path

from . import views

app_name = 'branding'

urlpatterns = [
    # Public
    path('', views.landing, name='landing'),
    path('my-requests/', views.my_requests, name='my_requests'),
    path('project/<int:pk>/progress/', views.client_project_progress, name='client_project_progress'),
    path('project/<int:pk>/messages/', views.client_messages, name='client_messages'),
    path('profile/', views.client_profile, name='client_profile'),
    path('wizard/', views.wizard, name='wizard'),
    path('wizard/step/<int:step>/', views.wizard_step, name='wizard_step'),
    path('wizard/autosave/', views.wizard_autosave, name='wizard_autosave'),
    path('wizard/upload/', views.upload_file, name='upload_file'),
    path('upload/<int:asset_id>/delete/', views.delete_asset, name='delete_asset'),

    # Staff dashboard (int pk routes must precede the request-number route)
    path('dashboard/', views.dashboard, name='dashboard'),
    path('kanban/', views.kanban, name='kanban'),
    path('kanban/move/', views.kanban_update, name='kanban_update'),
    path('requests/<int:pk>/', views.request_detail, name='request_detail'),
    path('requests/<int:pk>/assign/', views.assign_designer, name='assign_designer'),
    path('requests/<int:pk>/status/', views.update_status, name='update_status'),
    path('requests/<int:pk>/priority/', views.update_priority, name='update_priority'),
    path('requests/<int:pk>/delivery/', views.update_delivery, name='update_delivery'),
    path('requests/<int:pk>/notes/', views.update_internal_notes, name='update_internal_notes'),
    path('requests/<int:pk>/note/', views.add_note, name='add_note'),
    path('requests/<int:pk>/archive/', views.archive_request, name='archive_request'),
    path('requests/<int:pk>/edit/', views.edit_request, name='edit_request'),
    path('assets/<int:asset_id>/download/', views.download_asset, name='download_asset'),
    path('assets/<int:asset_id>/replace/', views.replace_asset, name='replace_asset'),
    path('asset-versions/<int:version_id>/download/', views.download_asset_version, name='download_asset_version'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('requests/<str:request_number>/', views.submitted, name='submitted'),

    # Messaging
    path('requests/<int:pk>/messages/send/', views.send_message, name='send_message'),
    path('requests/<int:pk>/messages/poll/', views.poll_messages, name='poll_messages'),
    path('requests/<int:pk>/messages/read/', views.mark_visible_read, name='mark_visible_read'),
    path('messages/<int:pk>/read/', views.mark_message_read, name='mark_message_read'),
    path('messages/<int:pk>/thread-read/', views.mark_thread_read, name='mark_thread_read'),
    path('messages/unread-count/', views.unread_message_count, name='unread_message_count'),

    # Feedback / Reviews
    path('requests/<int:pk>/feedback/', views.feedback_create, name='feedback_create'),
    path('feedback/<int:pk>/respond/', views.feedback_update, name='feedback_update'),
    path('feedback/', views.feedback_list, name='feedback_list'),

    # PDF Report
    path('requests/<int:pk>/pdf/', views.download_project_pdf, name='download_project_pdf'),

    # Analytics Report
    path('reports/analytics/', views.analytics_report, name='analytics_report'),

    # GDPR — Data export
    path('gdpr/export/', views.request_data_export, name='request_data_export'),
    path('gdpr/export/list/', views.data_export_list, name='data_export_list'),
    path('gdpr/export/<int:pk>/download/', views.download_data_export, name='download_data_export'),

    # GDPR — Consent
    path('gdpr/consent/', views.update_consent, name='update_consent'),
    path('gdpr/consent/history/', views.consent_history, name='consent_history'),
    path('gdpr/privacy/accept/', views.privacy_accept, name='privacy_accept'),

    # GDPR — Anonymization (staff)
    path('requests/<int:pk>/anonymize/', views.anonymize_request_view, name='anonymize_request'),

    # Email testing (staff)
    path('test-email/', views.test_email, name='test_email'),

    # Analytics Dashboard (staff)
    path('analytics/', views.analytics_overview, name='analytics_overview'),
    path('analytics/staff/', views.analytics_staff, name='analytics_staff'),
    path('analytics/collections/', views.analytics_collections, name='analytics_collections'),
    path('analytics/timeline/', views.analytics_timeline, name='analytics_timeline'),

    # Supervisor Dashboard
    path('supervisor/dashboard/', views.supervisor_dashboard, name='supervisor_dashboard'),
    path('supervisor/team/', views.supervisor_team, name='supervisor_team'),
    path('supervisor/team/pdf/', views.supervisor_team_pdf, name='supervisor_team_pdf'),
    path('supervisor/designer/<int:user_id>/', views.supervisor_designer_detail, name='supervisor_designer_detail'),

    # Designer Dashboard
    path('designer/dashboard/', views.designer_dashboard, name='designer_dashboard'),

    # Designer Workflow — Draft Uploads
    path('designer/requests/<int:pk>/drafts/', views.designer_drafts, name='designer_drafts'),
    path('designer/requests/<int:pk>/drafts/<int:draft_id>/', views.designer_draft_detail, name='designer_draft_detail'),

    # Designer Workflow — Feedback Requests
    path('designer/requests/<int:pk>/feedback-requests/', views.designer_feedback_requests, name='designer_feedback_requests'),
    path('designer/requests/<int:pk>/feedback-requests/<int:fr_id>/', views.designer_feedback_detail, name='designer_feedback_detail'),

    # Designer Workflow — Resources
    path('designer/resources/', views.designer_resources, name='designer_resources'),

    # Designer Workflow — Time Tracking
    path('designer/time/', views.designer_time_tracking, name='designer_time_tracking'),
    path('designer/time/export/', views.designer_export_timesheet, name='designer_export_timesheet'),

    # Designer Workflow — Notes & Journal
    path('designer/requests/<int:pk>/notes/', views.designer_notes, name='designer_notes'),

    # Designer Workflow — Templates
    path('designer/templates/', views.designer_templates, name='designer_templates'),

    # Designer Workflow — Collection Templates
    path('designer/collection-templates/', views.collection_template_list, name='collection_template_list'),
    path('designer/collection-templates/<int:collection_pk>/', views.collection_template_detail, name='collection_template_detail'),
    path('designer/collection-templates/<int:pk>/edit/', views.collection_template_edit, name='collection_template_edit'),
    path('designer/collection-templates/<int:pk>/delete/', views.collection_template_delete, name='collection_template_delete'),
    path('designer/collection-templates/<int:pk>/download/', views.collection_template_download, name='collection_template_download'),

    # Collaboration — Peer Review
    path('designer/requests/<int:pk>/peer-reviews/', views.peer_reviews, name='peer_reviews'),
    path('designer/requests/<int:pk>/peer-reviews/<int:review_id>/', views.peer_review_detail, name='peer_review_detail'),

    # Collaboration — Internal Comments
    path('designer/requests/<int:pk>/comments/', views.design_comments, name='design_comments'),
    path('designer/requests/<int:pk>/comments/mention-search/', views.comment_mention_search, name='comment_mention_search'),

    # Collaboration — Design Handoff
    path('designer/requests/<int:pk>/handoffs/', views.design_handoffs, name='design_handoffs'),
    path('designer/requests/<int:pk>/handoffs/<int:handoff_id>/', views.handoff_detail, name='handoff_detail'),

    # Collaboration — Knowledge Base
    path('designer/knowledge/', views.knowledge_base, name='knowledge_base'),
    path('designer/knowledge/<slug:slug>/', views.knowledge_detail, name='knowledge_detail'),

    # Collaboration — Design Showcase
    path('designer/showcase/', views.showcase, name='showcase'),
    path('designer/showcase/<int:showcase_id>/', views.showcase_detail, name='showcase_detail'),

    # Integrations — Figma
    path('designer/integrations/figma/', views.figma_integration, name='figma_integration'),

    # Integrations — Adobe CC
    path('designer/integrations/adobe/', views.adobe_integration, name='adobe_integration'),

    # Integrations — Design Tools
    path('designer/tools/colors/', views.design_tools_color, name='design_tools_color'),
    path('designer/tools/fonts/', views.design_tools_fonts, name='design_tools_fonts'),
    path('designer/tools/organizer/', views.design_tools_organizer, name='design_tools_organizer'),
    path('designer/tools/brand-check/', views.design_tools_brand_check, name='design_tools_brand_check'),

    # Integrations — Slack
    path('designer/integrations/slack/', views.slack_integration, name='slack_integration'),

    # Integrations — Calendar
    path('designer/integrations/calendar/', views.calendar_integration, name='calendar_integration'),

    # Unified Staff Dashboard
    path('staff/', views.unified_dashboard, name='unified_dashboard'),
    path('staff/switch-role/', views.switch_role_view, name='switch_role_view'),
    path('staff/save-layout/', views.save_layout, name='save_layout'),
    path('staff/save-positions/', views.save_widget_positions, name='save_widget_positions'),
    path('staff/add-widget/', views.add_widget, name='add_widget'),
    path('staff/widget/<int:widget_id>/remove/', views.remove_widget, name='remove_widget'),
    path('staff/widget/<int:widget_id>/collapse/', views.toggle_widget_collapse, name='toggle_widget_collapse'),
    path('staff/widget/<int:widget_id>/visibility/', views.toggle_widget_visibility, name='toggle_widget_visibility'),
    path('staff/widget/<int:widget_id>/data/', views.widget_data_api, name='widget_data_api'),
    path('staff/reset/', views.reset_dashboard, name='reset_dashboard'),

    # Designer Workflow System
    path('designer/workflow/', views.workflow_dashboard, name='workflow_dashboard'),
    path('designer/workflow/<int:pk>/', views.workflow_project, name='workflow_project'),
    path('designer/workflow/<int:pk>/advance/', views.workflow_advance_stage, name='workflow_advance_stage'),
    path('designer/workflow/<int:pk>/move/', views.workflow_move_stage, name='workflow_move_stage'),
    path('designer/workflow/<int:pk>/question/', views.workflow_add_question, name='workflow_add_question'),
    path('designer/workflow/<int:pk>/question/<int:q_id>/answer/', views.workflow_answer_question, name='workflow_answer_question'),
    path('designer/workflow/<int:pk>/feedback/', views.workflow_add_feedback, name='workflow_add_feedback'),
    path('designer/workflow/<int:pk>/feedback/<int:fb_id>/update/', views.workflow_update_feedback, name='workflow_update_feedback'),
    path('designer/workflow/<int:pk>/iteration/', views.workflow_add_iteration, name='workflow_add_iteration'),
    path('designer/workflow/<int:pk>/decision/', views.workflow_add_decision, name='workflow_add_decision'),
    path('designer/workflow/<int:pk>/communication/', views.workflow_add_communication, name='workflow_add_communication'),
    path('designer/workflow/<int:pk>/communication/<int:comm_id>/toggle-action/', views.workflow_toggle_action, name='workflow_toggle_action'),

    # ── Concept Presentation System ──────────────────────────────────────────
    path('request/<int:request_pk>/concepts/', views.concept_list, name='concept_list'),
    path('request/<int:request_pk>/concepts/create/', views.concept_create, name='concept_create'),
    path('request/<int:request_pk>/concepts/compare/', views.concept_compare, name='concept_compare'),
    path('request/<int:request_pk>/concepts/analysis/', views.concept_feedback_analysis, name='concept_feedback_analysis'),
    path('request/<int:request_pk>/concepts/decisions/', views.concept_decision_dashboard, name='concept_decision_dashboard'),
    path('request/<int:request_pk>/concepts/sessions/', views.concept_sessions, name='concept_sessions'),
    path('concept/<int:pk>/', views.concept_detail, name='concept_detail'),
    path('concept/<int:pk>/edit/', views.concept_edit, name='concept_edit'),
    path('concept/<int:pk>/present/', views.concept_present, name='concept_present'),
    path('concept/<int:pk>/recommend/', views.concept_recommend, name='concept_recommend'),
    path('concept/<int:pk>/archive/', views.concept_archive, name='concept_archive'),
    path('concept/<int:pk>/delete/', views.concept_delete, name='concept_delete'),
    path('concept/<int:pk>/image/<int:img_id>/delete/', views.concept_delete_image, name='concept_delete_image'),
    path('concept/<int:pk>/favorite/', views.concept_mark_favorite, name='concept_mark_favorite'),
    path('concept/<int:pk>/rate/', views.concept_rate_element, name='concept_rate_element'),
    path('concept/<int:pk>/annotate/', views.concept_add_annotation, name='concept_add_annotation'),
    path('concept/<int:pk>/annotation/<int:ann_id>/resolve/', views.concept_resolve_annotation, name='concept_resolve_annotation'),
    path('concept/<int:pk>/feedback/', views.concept_add_feedback, name='concept_add_feedback'),
    path('concept/<int:pk>/sticky-note/', views.concept_add_sticky_note, name='concept_add_sticky_note'),
    path('concept/<int:pk>/decide/', views.concept_decide, name='concept_decide'),
    path('concept/<int:pk>/refinements/', views.concept_refinements, name='concept_refinements'),
    path('concept/<int:pk>/refinement/<int:refinement_id>/iteration/', views.concept_add_iteration, name='concept_add_iteration'),
    path('concept/<int:pk>/refinement/<int:refinement_id>/iteration/<int:iteration_id>/approve/', views.concept_approve_iteration, name='concept_approve_iteration'),
    path('request/<int:pk>/session/<int:session_id>/update/', views.concept_session_update, name='concept_session_update'),

    # ── Intelligent Questionnaire System ─────────────────────────────────────
    path('request/<int:request_pk>/questionnaires/', views.questionnaire_list, name='questionnaire_list'),
    path('request/<int:request_pk>/questionnaires/create/', views.questionnaire_create, name='questionnaire_create'),
    path('request/<int:request_pk>/questionnaires/from-template/<int:template_id>/', views.questionnaire_from_template, name='questionnaire_from_template'),
    path('request/<int:request_pk>/questionnaires/analytics/', views.questionnaire_analytics, name='questionnaire_analytics'),
    path('request/<int:request_pk>/questionnaires/decisions/', views.decision_points, name='decision_points'),
    path('request/<int:request_pk>/questionnaires/profile/<int:client_id>/', views.preference_profile, name='preference_profile'),
    path('questionnaire/<int:pk>/', views.questionnaire_detail, name='questionnaire_detail'),
    path('questionnaire/<int:pk>/edit/', views.questionnaire_edit, name='questionnaire_edit'),
    path('questionnaire/<int:pk>/send/', views.questionnaire_send, name='questionnaire_send'),
    path('questionnaire/<int:pk>/reminder/', views.questionnaire_reminder, name='questionnaire_reminder'),
    path('questionnaire/<int:pk>/add-question/', views.questionnaire_add_question, name='questionnaire_add_question'),
    path('questionnaire/<int:pk>/bulk-add/', views.questionnaire_bulk_add, name='questionnaire_bulk_add'),
    path('questionnaire/<int:pk>/answers/', views.questionnaire_answers, name='questionnaire_answers'),
    path('questionnaire/<int:pk>/export/', views.questionnaire_export, name='questionnaire_export'),
    path('questionnaire/<int:pk>/suggest/', views.questionnaire_smart_suggest, name='questionnaire_smart_suggest'),
    path('questionnaire/<int:pk>/reorder/', views.questionnaire_reorder_questions, name='questionnaire_reorder_questions'),
    path('questionnaire/question/<int:qid>/edit/', views.questionnaire_edit_question, name='questionnaire_edit_question'),
    path('questionnaire/question/<int:qid>/delete/', views.questionnaire_delete_question, name='questionnaire_delete_question'),
    path('questionnaire/decision/<int:pk>/update/', views.decision_point_update, name='decision_point_update'),
    path('q/<str:token>/', views.client_questionnaire, name='client_questionnaire'),
    path('q/<str:token>/submit/', views.client_questionnaire_submit, name='client_questionnaire_submit'),
    path('q/<str:token>/answer/<int:qid>/', views.client_question_answer, name='client_question_answer'),
    path('q/<str:token>/decision/<int:dp_id>/', views.client_decision_respond, name='client_decision_respond'),
    path('questionnaire-templates/', views.questionnaire_templates_list, name='questionnaire_templates_list'),
    path('questionnaire-templates/create/', views.questionnaire_template_create, name='questionnaire_template_create'),
]
