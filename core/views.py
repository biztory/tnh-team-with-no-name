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

    # selected_viz = visualizations[len(visualizations) - 1] if visualizations else None

    dashboards = tableau_next_api.get_entities_through_soql(connection=next_api_connection, entity_type="AnalyticsDashboard")

    selected_dashboard = dashboards[len(dashboards) - 1] if dashboards else None

    viz_image_response = tableau_next_api.post_image_download(connection_dict=next_api_connection, asset=selected_dashboard, metadata_only=False)
    viz_image_bytes = viz_image_response.get("image_bytes")

    # Create a response that displays the image we just downloaded
    response = HttpResponse(content_type="image/png")
    response.write(viz_image_bytes)
    return response