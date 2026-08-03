from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Signup
    path('signup/', views.signup, name='signup'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('login/', views.login_view, name='login_view'),
    path('logout/', views.logout_view, name='logout'),
    path('verify-email/<str:uidb64>/<str:token>/', views.verify_email, name='verify_email'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_dashboard, name='profile_dashboard'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/notifications/', views.notification_preferences, name='notification_preferences'),
    path('profile/delete/', views.delete_account, name='delete_account'),
    path('profile/security/two-factor/', views.two_factor_settings, name='two_factor_settings'),
    path('profile/security/api-keys/', views.api_keys, name='api_keys'),
    path('profile/consultations/', views.consultations_list, name='consultations_list'),

    # Password reset URLs
    path('password-reset/', views.UserPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', views.UserPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', views.UserPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('password-reset/complete/', views.UserPasswordResetCompleteView.as_view(), name='password_reset_complete'),
]
