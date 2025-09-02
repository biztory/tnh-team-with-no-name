# imports - Python/general
from datetime import datetime, timezone
import traceback
import requests, os, copy

# imports - Django
from django.contrib.auth.base_user import AbstractBaseUser
from django.conf import settings

# imports - Orbit One
# Models
# N/A
# Functions
from tableau_next_question.functions import log_and_display_message

def connect() -> dict:

    sf_ext_client_app_consumer_key = settings.SF_EXT_CLIENT_APP_CONSUMER_KEY
    sf_ext_client_app_consumer_secret = settings.SF_EXT_CLIENT_APP_CONSUMER_SECRET
    sf_ext_client_app_redirect_uri = settings.SF_EXT_CLIENT_APP_REDIRECT_URI
    sf_org_domain = settings.SF_ORG_DOMAIN
    # sf_connect_user_username = os.getenv("sf_connect_user_username")
    # sf_connect_user_password = os.getenv("sf_connect_user_password")

    log_and_display_message(f"Salesforce External Client App Consumer Key: { sf_ext_client_app_consumer_key }\nSalesforce Org Domain: { sf_org_domain }\n")

    # Step 1: Authenticate using JWT Bearer Token Flow
    log_and_display_message("Authenticating using JWT Bearer Token Flow...")

    response = requests.post(
        f"{sf_org_domain}services/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": sf_ext_client_app_consumer_key,
            "client_secret": sf_ext_client_app_consumer_secret,
        },
    )

    if response.status_code != 200:
        log_and_display_message(f"Error: {response.status_code} - {response.text}")
        return {}

    response_data = response.json()
    access_token = response_data.get("access_token")
    instance_url = response_data.get("instance_url")
    
    connect_api_base_url = f"{instance_url}/services/data/v64.0"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    session = requests.Session()
    session.headers.update(headers)
    connection_dict = {
        "session": session,
        "headers": headers,
        "instance_url": instance_url,
        "connect_api_base_url": connect_api_base_url
    }
    log_and_display_message("Authentication successful.")

    return connection_dict

def list_workspaces(connection_dict: dict) -> list:
    """
    List all workspaces in the Tableau Next API.
    """

    connect_api_get_workspaces_url = f"{ connection_dict['connect_api_base_url'] }/tableau/workspaces"

    response = connection_dict["session"].get(connect_api_get_workspaces_url)
    response_data = response.json()

    return response_data.get("workspaces", [])

def get_workspace_asset_collection(connection_dict: dict, workspace_id: str) -> list:
    """
    List all assets in a specific workspace.
    """

    connect_api_get_assets_url = f"{ connection_dict['connect_api_base_url'] }/tableau/workspaces/{workspace_id}/assets"

    response = connection_dict["session"].get(connect_api_get_assets_url)
    response_data = response.json()

    return response_data.get("workspaceAssets", [])

def post_image_download(connection_dict: dict, asset: dict, metadata_only:bool=False) -> dict|requests.Response:
    """
    Post a request to download an image or metadata of a specific asset.

    Note the discrepancies between Dashboard and Submetric. This is probably because currently Dashboard comes from the "new" Tableau Next REST API, but Submetric comes from the "old" Salesforce SSOT data we're accessing.
    """

    connect_api_post_image_download_url = f"{ connection_dict['connect_api_base_url'] }/tableau/download"

    metadata_only_query_param = "?metadataOnly=true" if metadata_only else "?metadataOnly=false"
    connect_api_post_image_download_url += metadata_only_query_param

    # Determine asset_type
    # For dashboard, this will be in attributes -> type. 
    asset_type_from_attributes = asset.get("attributes", {}).get("type")
    if asset_type_from_attributes is not None:
        asset_type = asset_type_from_attributes
    # Otherwise, if we have an insightsSettings key/dict as part of our assets, it's a metric (which is called Submetric here)
    else:
        insights_settings = asset.get("insightsSettings", {})
        if insights_settings:
            asset_type = "Submetric"

    # The values and body are different depending on whether we're dealing with a dashboard or a metric
    connect_api_post_image_body = {}
    if asset_type == "AnalyticsDashboard":
        asset_type_for_request = "Dashboard"
        # Determine asset_name
        asset_name = ""
        asset_name_from_developer_name = asset.get("DeveloperName")
        if asset_name_from_developer_name is not None:
            asset_name = asset_name_from_developer_name

        connect_api_post_image_body = {
            "asset": {
                "dashboardName": asset_name,
                "type": asset_type_for_request
            }
        }
    
    elif asset_type == "Submetric":
        asset_type_for_request = "Submetric"
        connect_api_post_image_body = {
            "asset": {
                "assetId": asset.get("id"),
                "type": asset_type_for_request
            }
        }
        
    response = connection_dict["session"].post(connect_api_post_image_download_url, json=connect_api_post_image_body)
    
    if response.status_code != 200:
        log_and_display_message(f"Error downloading data: {response.status_code} - {response.text}")
        # Yes, but we know this happens, because the Tableau Next API is not working yet. So we'll cheat and return an image we already have.
        new_response = copy.deepcopy(response)
        new_response.status_code = 200
        sample_image_location = "resources/biztory_team_members_strava_data.png"
        sample_image_content = open(sample_image_location, "rb").read()
        new_response._content = sample_image_content
        return new_response
    
    if metadata_only:
        return response.json()
    else:
        return response

def get_all_semantic_models(connection_dict: dict) -> dict:
    """
    Get a specific semantic model by its ID.
    """

    connect_api_get_semantic_model_url = f"{ connection_dict['connect_api_base_url'] }/ssot/semantic/models"

    response = connection_dict["session"].get(connect_api_get_semantic_model_url)
    
    if response.status_code != 200:
        log_and_display_message(f"Error getting semantic model: {response.status_code} - {response.text}")
        return {}

    return response.json()

def get_semantic_model_metadata(connection_dict: dict, semantic_data_model:dict) -> dict:
    """
    Get additional metadata about a semantic model, including information about its fields (in semanticDataObjects).

    `connection_dict`: The connection dictionary containing the base URL and session information.
    `semantic_data_model`: The semantic data model for which we want to retrieve contents.
    """

    connect_api_get_semantic_model_contents_url = f"{ connection_dict['connect_api_base_url'] }/ssot/semantic/models/{ semantic_data_model.get('apiName') }"

    response = connection_dict["session"].get(connect_api_get_semantic_model_contents_url)

    if response.status_code != 200:
        log_and_display_message(f"Error getting semantic model contents: {response.status_code} - {response.text}")
        return []

    return response.json()

def get_metric_metadata(connection_dict:dict, semantic_data_model:dict, metric_api_name:str) -> dict:
    """
    Get information on a Metric defined as part of a Semantic Model.

    `connection_dict`: The connection dictionary containing the base URL and session information.
    `semantic_data_model`: The semantic data model for which we want to retrieve contents.
    `metric_api_name`: The API name of the metric we want to retrieve.
    """

    connect_api_get_semantic_model_contents_url = f"{ connection_dict['connect_api_base_url'] }/ssot/semantic/models/{ semantic_data_model.get('apiName') }/metrics/{ metric_api_name }"

    response = connection_dict["session"].get(connect_api_get_semantic_model_contents_url)

    if response.status_code != 200:
        log_and_display_message(f"Error getting semantic model metric contents: {response.status_code} - {response.text}")
        return []

    return response.json()

def get_visualization_collection(connection_dict: dict) -> list:
    """
    Get a collection of visualizations.
    """

    connect_api_get_visualizations_url = f"{ connection_dict['connect_api_base_url'] }/tableau/visualizations"

    # Bug fix/workaround: this is not available in v64.0; we need to also specify ?minorVersion=-1.
    connect_api_get_visualizations_url = f"{ connect_api_get_visualizations_url}?minorVersion=-1"

    response = connection_dict["session"].get(connect_api_get_visualizations_url)
    
    if response.status_code != 200:
        log_and_display_message(f"Error getting visualizations: {response.status_code} - {response.text}")
        return []

    return response.json().get("visualizations", [])

def get_visualization(connection_dict: dict, asset_id_or_name: str) -> dict:
    """
    Get a specific visualization by its ID.
    """

    connect_api_get_visualization_url = f"{ connection_dict['connect_api_base_url'] }/tableau/visualizations/{asset_id_or_name}"
    # Bug fix/workaround: this is not available in v64.0; we need to also specify ?minorVersion=-1.
    connect_api_get_visualization_url = f"{ connect_api_get_visualization_url}?minorVersion=-1"

    response = connection_dict["session"].get(connect_api_get_visualization_url)
    
    if response.status_code != 200:
        log_and_display_message(f"Error getting visualization: {response.status_code} - {response.text}")
        return {}

    return response.json()

def post_visualization(connection_dict: dict, visualization_definition) -> dict:
    """
    Post a new visualization to the Tableau Next API.
    """

    connect_api_post_visualization_url = f"{ connection_dict['connect_api_base_url'] }/tableau/visualizations"

    # Bug fix/workaround: this is not available in v64.0; we need to also specify ?minorVersion=-1.
    connect_api_post_visualization_url = f"{ connect_api_post_visualization_url}?minorVersion=-1"

    response = connection_dict["session"].post(connect_api_post_visualization_url, json=visualization_definition)

    if response.status_code != 201:
        raise Exception(f"Error posting visualization: {response.status_code} - {response.text}")

    return response.json()
    
# Useful in case there's info we _can't_ get with the "official" Tableau Next API: we can still use SOQL
def get_entities_through_soql(connection:dict, entity_type:str) -> list:
    """
    Get entities of a certain type from Tableau Next via SOQL through the Salesforce API/REST API connection. Returns a list of dicts, each dict representing an entity.

    Also implemented pagination for large result sets.

    Entity Types supported include but are not limited to: AnalyticsDashboard, AnalyticsDashboardWidget, AnalyticsVizWidgetDef, AnalyticsVisualization
    """

    log_and_display_message(f"Getting entities of type { entity_type } from Tableau Next/Salesforce via SOQL through the REST API.")

    entities = []

    query_for_entities = f"SELECT+FIELDS(Standard)+FROM+{ entity_type }"

    request_url_base = f"{ connection['instance_url'] }/services/data/v64.0/query?q={ query_for_entities }"
    request_url = request_url_base

    fetched_all_records = False

    while not fetched_all_records:
        response = connection['session'].get(url=request_url)
        if response.ok:
            response_json = response.json()
            entities += response_json.get("records", [])
            if "nextRecordsUrl" in response_json:
                request_url = f"{ connection['instance_url'] }{ response_json['nextRecordsUrl'] }"
            else:
                fetched_all_records = True
        else:
            raise Exception(f"The response from the API, while trying to fetch { entity_type }, was not ok.\n\t{ response.text }")

    return entities