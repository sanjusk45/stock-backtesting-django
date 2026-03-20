from django.urls import path
from . import views

urlpatterns = [
    path('',          views.index,       name='index'),
    path('run/',      views.run,         name='run'),
    path('live/',     views.live_quote,  name='live_quote'),
    path('download/', views.download_csv,name='download_csv'),
    path('compare/',  views.compare,     name='compare'),
]
