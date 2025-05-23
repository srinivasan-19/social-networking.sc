from django.urls import path
from . import views

urlpatterns = [

    path("", views.inbox, name="inbox"),
    path("api/authors/<uuid:object_author_serial>/inbox/", views.inboxApi, name="follow_request"), # sender of the follow request
    
]