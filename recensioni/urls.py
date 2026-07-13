from django.urls import path
from . import views

urlpatterns = [
    path('crea/<int:escursione_id>/', views.crea_recensione, name='crea_recensione'),
    path('rispondi/<int:recensione_id>/', views.rispondi_recensione, name='rispondi_recensione'),
    path('segnala/<int:recensione_id>/', views.segnala_recensione, name='segnala_recensione'),
]