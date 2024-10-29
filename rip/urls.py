
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from baggage_registration import views
from rip import settings
from baggage_registration.views import *
from rest_framework import routers

router = routers.DefaultRouter()

urlpatterns = [
    path('api/baggages/', get_baggages_list, name='get_baggages_list'),  # GET
    path('api/baggages/<int:baggage_id>/', get_baggage_by_id, name='get_baggage_by_id'),  # GET
    path('api/baggages/create/', create_baggage, name='create_baggage'),  # POST
    path('api/baggages/<int:baggage_id>/update/', update_baggage, name='update_baggage'),  # PUT
    path('api/baggages/<int:baggage_id>/delete/', delete_baggage, name='delete_baggage'),  # DELETE
    path('api/baggages/<int:baggage_id>/update_image/', update_baggage_image, name='update_image'),  # POST
    path('api/baggages/<int:baggage_id>/add_baggage_to_transfer/', add_baggage_to_transfer, name='add_baggage_to_transfer'), # POST

    # Набор методов для заявок
    path('api/transfers/', get_transfers_list, name=' get_transfers_list'),  # GET
    path('api/transfers/<int:transfer_id>/', get_transfer_by_id, name='get_transfer_by_id'),  # GET
    path('api/transfers/<int:transfer_id>/update/', update_transfer, name='update_transfer'),  # PUT
    path('api/transfers/<int:transfer_id>/update_status_user/', update_status_user, name='update_status_user'), # PUT
    path('api/transfers/<int:transfer_id>/update_status_admin/', update_status_admin, name='update_status_admin'), # PUT
    path('api/transfers/<int:transfer_id>/delete/', delete_transfer, name='delete_transfer'),  # DELETE

    # Набор методов для м-м
    path('api/baggage/<int:baggage_id>/transfer/<int:transfer_id>/update_baggage_transfer/', update_baggage_transfer, name='update_baggage_transfer'),  # PUT
    path('api/baggage/<int:baggage_id>/transfer/<int:transfer_id>/delete_baggage_transfer/', delete_baggage_from_transfer, name='delete_baggage_transfer'),  # DELETE

    # Набор методов пользователей
    path('api/users/register/', register, name='register'),  # POST
    path('api/users/login/', login, name='login'),  # POST
    path('api/users/logout/', logout, name='logout'),  # POST
    path('api/users/<int:user_id>/update/', update_user, name='update_user'),  # PUT
]
