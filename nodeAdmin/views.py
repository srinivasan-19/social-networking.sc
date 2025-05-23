from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, HttpResponseNotFound
from author.models import Author
from django.conf import settings
import json


