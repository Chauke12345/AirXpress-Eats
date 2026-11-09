from django.contrib import admin
from django.urls import include, path, re_path
from django.conf import settings
from django.views.static import serve
from django.http import HttpResponseNotFound



def deny_private_driver_media(request, *args, **kwargs):
    return HttpResponseNotFound()
urlpatterns = [

    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "",
        include("orders.urls"),
    ),

]

urlpatterns += [
    re_path(
        r"^media/driver_licenses(?:/.*)?$",
        deny_private_driver_media,
    ),
    re_path(
        r"^media/(?P<path>.*)$",
        serve,
        {
            "document_root": settings.MEDIA_ROOT,
        },
    ),
]
