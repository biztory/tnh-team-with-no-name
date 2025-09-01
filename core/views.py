from django.shortcuts import render

# Create your views here.
from django.http import HttpRequest, HttpResponse

import core.functions.tableau.next_api as tableau_next_api

def index(request: HttpRequest) -> HttpResponse:
    return HttpResponse("Hello, il mondo.")

def test(request:HttpRequest) -> HttpResponse:
    """
    Used to e.g. kick off a function that we might want to debug.
    """

    next_api_connection = tableau_next_api.connect()

    visualizations = tableau_next_api.get_visualization_collection(connection_dict=next_api_connection)

    selected_viz = visualizations[len(visualizations) - 1] if visualizations else None

    return HttpResponse("This is a test page.")