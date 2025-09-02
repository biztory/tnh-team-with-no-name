# imports - Python/general
import requests

# imports - Django
from django.conf import settings

# imports - our app
# Models

# Functions
from tableau_next_question.functions import log_and_display_message

# REST API-related functionality

def connect() -> dict:
    """
    Connect to the Tableau Server/Cloud REST API, normally using the PAT stored in the settings. Returns a dict containing a number of useful connection attributes including the session token, site_id, etc. Most importantly, the Session is also returned and should probably be used for most future requests.
    """

    tableau_server_url = settings.TABLEAU_SERVER_URL
    tableau_api_version = settings.TABLEAU_API_VERSION
    tableau_site_content_url = settings.TABLEAU_SITE_CONTENT_URL
    tableau_pat_name = settings.TABLEAU_PAT_NAME
    tableau_pat_secret = settings.TABLEAU_PAT_SECRET

    log_and_display_message(f"Authenticating to REST API for Tableau Server: { tableau_server_url } (\"{ tableau_site_content_url }\").")

    session = requests.Session()

    connection = {}
    tableau_api_url = f"{ tableau_server_url }/api/{ tableau_api_version }" # Start with this version; we'll get a more accurate "measurement" later on.
    tableau_site = tableau_site_content_url

    request_json = {
        "credentials": {
            "personalAccessTokenName": tableau_pat_name,
            "personalAccessTokenSecret": tableau_pat_secret,
            "site": {
                "contentUrl": tableau_site
            }
        }
    }

    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    request_url = f"{ tableau_api_url }/auth/signin"
    response = session.post(url=request_url, json=request_json, headers=request_headers)

    if not response.ok:
        if "error" in response.json():
            error_message = f"{ response.json()['error'].get('code') } { response.json()['error'].get('summary') }: { response.json()['error'].get('detail') }"
        else:
            error_message = response.text
        raise Exception(f"Unable to authenticate to the REST API on \"{ tableau_api_url }\". The response was:<br /><code>{ error_message }</code>")

    # Then get what we need.
    tableau_api_token = response.json().get("credentials", {}).get("token", "")

    # Why don't we prepare and share the headers as well...
    request_headers["X-Tableau-Auth"] = tableau_api_token
    session.headers.update(request_headers)

    connection = {
        "session": session,
        "tableau_url": tableau_server_url,
        "tableau_api_url": tableau_api_url,
        "tableau_site": tableau_site,
        "tableau_site_id": response.json().get("credentials", {}).get("site", {}).get("id", ""),
        "tableau_site_content_url": response.json().get("credentials", {}).get("site", {}).get("contentUrl", ""),
        "tableau_user_id": response.json().get("credentials", {}).get("user", {}).get("id", ""),
        "token": tableau_api_token,
        "headers": request_headers
    }

    return connection

def disconnect(rest_api_connection:dict):
    """Invalidate a session that was spawned from a REST API token."""
    log_and_display_message(f"Signing out of REST API session on \"{ rest_api_connection['tableau_api_url'] }\".")
    try:
        request_url = f"{ rest_api_connection['tableau_api_url'] }/auth/signout"
        response = rest_api_connection["session"].get(url=request_url)
        return response.json()
    except Exception as e:
        log_and_display_message(f"Didn't manage to disconnect our REST API session:\n\t{e}")
        return {}

def fetch_paginated(entity_type:str, rest_api_connection:dict, page_size:int=200, for_entity_luid:str="", filter_expression:str="") -> list:
    """
    Function for generic fetching of Tableau entities in an environment. The entity type is expected to be plural ("projects", "workbooks", "flows", "datasources", "users", ...). We will specifically ask Tableau to return _all_ fields where supported (https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_concepts_fields.htm).

    This is the pagination method to be used with most of the "traditional" entity types on Tableau: workbooks, projects, etc. In fact, at this point the only entity types using a different pagination method are Pulse-related. See the fetch_paginated_with_token() function below.

    for_entity_luid applies to functions where a specific entity type has to be retrieved on a per-entity-basis. This is currently applicable to favorites, which is to be retrieved on a per-user basis. Also for group memberships which is... per group.

    A filter_expression can be provided, following the standard syntax for the Tableau REST API. See: https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_concepts_filtering_and_sorting.htm
    For example, to get data sources from only one specific project name, you could use: filter_expression="projectName:eq:My+Project+Name"
    """
    
    log_and_display_message(f"Getting all entities of type { entity_type } with pagination through REST API session on \"{ rest_api_connection['tableau_api_url'] }\".")

    # Pagination
    # We used to define page_size here, but it is now a function argument with a default of 200.
    page_number = 1
    total_returned = 0
    done = False

    if entity_type in ["schedules"]: # Schedules are Server-level (not Site) and has a different URI
        items_url = f"{rest_api_connection['tableau_api_url']}/{entity_type}"
    elif entity_type in ["site"]: # site = Site Settings are special too - just fetch the "top-level" resource. Not that we'd use these right away...
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}"
    elif entity_type in ["extractRefreshes", "flowRuns"]: # This is a "special" endpoint, it would seem? Kind of a task subtype. No pagination, either.
        asset_type_for_url = "runFlow" if entity_type == "flowRuns" else entity_type # Thanks Tableau!!! This is ridiculous
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/tasks/{asset_type_for_url}"
    # Favorites. You can only get favorites _for a user_.
    elif entity_type in ["favorites"]: # Different URL specifying the user id, which is required.
        if len(for_entity_luid) == 0:
            # If no user was passed to the function... we'll just do the one who's signed in.
            for_entity_luid = rest_api_connection['tableau_user_id']
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/favorites/{for_entity_luid}"
    elif entity_type in ["group_memberships"]: # Different URL specifying the group id
        if len(for_entity_luid) == 0:
            # If no group was passed to the function... we'll just do the one who's signed in.
            raise Exception(f"Group Memberships require a group ID to be passed to the function.")
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/groups/{for_entity_luid}/users"
    # A bit of an exception, perhaps, but we also have the ability to pull recommendations (which are always user-specific, hence we should use this with impersonation.) In this case, we're pulling views specifically but we could extend this later.
    # ACTUALLY. This does not work with CA, because it's not supported by its scoping. To be used later when Tableau does support it.
    elif entity_type in ["recommendations"]: # Different URL specifying the user id
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/recommendations?type=view"
    else:
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/{entity_type}"
    all_items = []

    while not done:
        # Different URL _structures_?
        if entity_type in ["datasources", "workbooks"]: # Datasources do not support the fields=_all_ specification, apparently. Also, we were having some trouble with workbooks, so here's to hoping we didn't need that.
            request_url = items_url + f"?pageSize={page_size}&pageNumber={page_number}"
        elif entity_type in ["extractRefreshes", "flowRuns"]: # extractRefresh tasks do not seem to support or need (?) pagination.
            request_url = items_url + f"?fields=_all_"
        else:
            request_url = items_url + f"?pageSize={page_size}&pageNumber={page_number}&fields=_all_"
        # And finally, do we need to append anything?
        if entity_type == "views":
            request_url += "&includeUsageStatistics=true"
        # And finally finally, do we have a filter expression?
        if len(filter_expression) > 0:
            request_url += f"&filter={ filter_expression }"
        
        response = rest_api_connection["session"].get(url=request_url) # No try/catch here, the errors are caught outside.
        response_json = response.json()

        if entity_type in ["site"]:
            return [response_json[entity_type]] # List with one item to adhere to the structure of other assets
        # extractRefreshes is _really_ a subtype of tasks, though the response _is_ tasks
        elif entity_type in ["extractRefreshes", "flowRuns"] and len(response_json["tasks"]) > 0:
            all_items += response_json["tasks"]["task"] # List with one item to adhere to the structure of other assets. It would seem pagination does not apply to tasks, but we were only able to test with a relatively small number of them.
        elif entity_type in ["group_memberships"]:
            all_items += response_json.get("users", {}).get("user", [])
            # Note to future self (you are going to love this): if you land here investigating a 401 error that occurs during Insight Messaging with a Group Delivery Config, it's probably because our REST API session is impersonating the owner of the IM, which may not be a site admin. If that's the case, they do not have permissions to read group memberships. We'll need to consider two options: sync group memberships with Connect and then just read those here (seems proferrable), or switch our REST API session back and forth to the admin user to get memberships (seems... weird).
        else:
            if entity_type not in ["extractRefreshes", "flowRuns"] and int(response_json.get("pagination", {}).get("totalAvailable", 1)) > 0: # Assume we got _something_ back if there is no real pagination.
                all_items += response_json.get(entity_type, {}).get(entity_type[:-1], []) # += concatenates lists while .append creates lists of lists. The list index thingy [:-1] cuts of a character to get the singular
            else:
                return []
        # Pagination logic
        total_available = int(response_json.get("pagination", {}).get("totalAvailable", 1))
        page_number += 1
        total_returned += page_size
        if total_returned >= total_available:
            done = True
    
    return all_items

def fetch_entity(entity_luid:str, entity_type:str, rest_api_connection:dict, for_user_luid:str="") -> list:
    """
    Function for generic fetching of one Tableau entity in an environment. The entity type is expected to be plural ("projects", "workbooks", "flows", "datasources", "users", ...). We will specifically ask Tableau to return _all_ fields where supported (https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_concepts_fields.htm).

    for_user_luid applies to functions where a specific entity type has to be retrieved on a per-user-basis. This is currently applicable to favorites.
    """
    
    log_and_display_message(f"Getting single entities of type { entity_type } with ID \"{ entity_luid }\" through REST API session on \"{ rest_api_connection['tableau_api_url'] }\".")

    if entity_type in ["schedules"]: # Schedules are Server-level (not Site) and has a different URI
        items_url = f"{rest_api_connection['tableau_api_url']}/{entity_type}"
    elif entity_type in ["site"]: # site = Site Settings are special too - just fetch the "top-level" resource. Not that we'd use these right away...
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}"
    elif entity_type in ["extractRefreshes", "flowRuns"]: # This is a "special" endpoint, it would seem? Kind of a task subtype. No pagination, either.
        asset_type_for_url = "runFlow" if entity_type == "flowRuns" else entity_type # Thanks Tableau!!! This is ridiculous
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/tasks/{asset_type_for_url}"
    # Favorites. You can only get favorites _for a user_.
    elif entity_type in ["favorites"]: # Different URL specifying the user id
        if len(for_user_luid) == 0:
            # If no user was passed to the function... we'll just do the one who's signed in.
            for_user_luid = rest_api_connection['tableau_user_id']
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/favorites/{for_user_luid}"
    # A bit of an exception, perhaps, but we also have the ability to pull recommendations (which are always user-specific, hence we should use this with impersonation.) In this case, we're pulling views specifically but we could extend this later.
    # ACTUALLY. This does not work with CA, because it's not supported by its scoping. To be used later when Tableau does support it.
    elif entity_type in ["recommendations"]: # Different URL specifying the user id
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/recommendations?type=view"
    else:
        items_url = f"{rest_api_connection['tableau_api_url']}/sites/{rest_api_connection['tableau_site_id']}/{entity_type}"

    # We still return a list for compatibility with other "levels"
    all_items = []

    # The entity ID, if not site or schedules.
    if entity_type not in ["schedules", "site"]:
        request_url = f"{ items_url }/{ entity_luid }?fields=_all_"
    else:
        request_url = f"{ items_url }"

    if entity_type == "views":
        request_url += "&includeUsageStatistics=true"
        
    response = rest_api_connection["session"].get(url=request_url) # No try/catch here, the errors are caught outside.
    response_json = response.json()

    if entity_type in ["site"]:
        return [response_json[entity_type]] # List with one item to adhere to the structure of other assets
    # extractRefreshes is _really_ a subtype of tasks, though the response _is_ tasks
    elif entity_type in ["extractRefreshes", "flowRuns"] and len(response_json["tasks"]) > 0:
        all_items += response_json["tasks"]["task"] # List with one item to adhere to the structure of other assets. It would seem pagination does not apply to tasks, but we were only able to test with a relatively small number of them.
    else:
        if entity_type not in ["extractRefreshes", "flowRuns"] and int(response_json.get("pagination", {}).get("totalAvailable", 1)) > 0: # Assume we got _something_ back if there is no real pagination.
            all_items = [response_json.get(entity_type[:-1], [])] # += concatenates lists while .append creates lists of lists. The list index thingy [:-1] cuts of a character to get the singular
        else:
            return []
    
    return all_items

def download_view_image(rest_api_connection:dict, view_luid:str, no_cache:bool=False, filters: list[tuple[str, str]]=[]) -> bytes:
    """
    Download the image of a view in PNG format.
    
    Args:
        rest_api_connection (`dict`): The connection to use for this action.
        view_luid (`str`): the LUID of the view to be downloaded.
        no_cache (`bool`): when set to True, we'll try to avoid Tableau's cache by requesting an image with maxAge of 1 minute.
        filters (`list` of `tuple`s): A list of tuples with the filter (field) name and value. This is used to apply filters to the image. No need to pass the vf_ prefix to the field name. See the Tableau documentation for more information on how these filters are applied: https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_concepts_filtering_and_sorting.htm#Filter-query-views
    
    Returns:
        The downloaded image (PNG) in bytes format. Well, actually the response, but response.content is the image.

    Raises:
        Exceptions sometimes.
    
    """
    
    request_url = f"{ rest_api_connection['tableau_api_url'] }/sites/{ rest_api_connection['tableau_site_id'] }/views/{ view_luid }/image"

    if no_cache:
        request_url += "?maxAge=1"

    if len(filters) > 0:
        starting_character = "&" if no_cache else "?"
        filter_string = "&".join([f"vf_{ filter[0] }={ filter[1] }" for filter in filters])
        request_url += f"{ starting_character }{ filter_string }"

    log_and_display_message(f"Downloading image from \"{ request_url }\".")
    response = rest_api_connection["session"].get(url=request_url)
    return response


def download_file(rest_api_connection:dict, asset_type:str, luid:str, format:str) -> requests.Response: # Or should we return Entity?
    """
    Download the file "behind" a data source, workbook, or flow.
    
    Args:
        rest_api_connection (`dict`): The connection to use for this action.
        asset_type (`str`): The type of the asset to download, plural (e.g., "workbooks", "datasources", "flows").
        luid (`str`): The LUID of the entity to download.
        format (`str`): Whether to include the extract in the file, if applicable (data source, workbook). `no_extract` does not include the extract. `yes_extract` includes the extract. Note that this is not directly related to the format of the entity (tds or twb vs tdsx or twbx), which instead is determined by how the author saved the document in the first place.
    
    Returns:
        The downloaded file in bytes format.

    Raises:
        Havoc.
    
    """

    includeExtract_value = "True" if format == "yes_extract" else "False"
    request_url = f"{ rest_api_connection['tableau_api_url'] }/sites/{rest_api_connection['tableau_site_id']}/{ asset_type }/{ luid }/content?includeExtract={ includeExtract_value }"
    log_and_display_message(f"Downloading { asset_type } file from \"{ request_url }\".")
    response = rest_api_connection["session"].get(url=request_url)
    return response
