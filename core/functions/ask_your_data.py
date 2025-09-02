# imports - Python/general
import traceback
import re, json, copy
import xml.etree.ElementTree as ET
from pydantic import BaseModel

# imports - Django
from django.contrib.auth import get_user_model
from django.conf import settings
User = get_user_model()

# imports - TNQ
# Models and Classes
from core.models import SlackCredential
# Functions
from tableau_next_question.functions import log_and_display_message
import core.functions.openai as openai
import core.functions.slack as slack
# import core.functions.entity_search as entity_search
# import core.functions.tableau.vizql_data_service as vizql_data_service
from core.functions.helpers import FormattedMessage
from core.functions.helpers_other import remove_fields_from_dictionary
import core.functions.prompts as ai_prompts
import core.functions.tableau.next_api as tableau_next_api
import core.functions.tableau.next_functions as tableau_next_functions
import core.functions.templates.tableau_next as tableau_next_templates
import core.functions.tableau.metadata_api as tableau_metadata_api
import core.functions.tableau.rest_api as tableau_rest_api
import core.functions.tableau.documents as tableau_documents

def respond_to_data_question(source:str, question:str, kwargs:dict) -> None:

    """
    Respond to a data question from a user in Slack. Note that currently only Slack is supported, other IM tools may be added in the future.
    
    `question` is to contain the question written by the user, which can be further narrowed down by our function here.

    `kwargs` is a dictionary containing additional information that may vary depending on the source. For example, in Slack, it may contain the user ID. It will help us respond in the right manner.
    """
    
    if source == "slack":
        slack_credential = SlackCredential.objects.first()
        # Get the attributes we need to respond, from the "kwargs"
        slack_channel = kwargs.get("slack_channel", None)
        first_name = kwargs.get("first_name", "")
        slack_user_id = kwargs.get("slack_user_id", None)
        thread_ts = kwargs.get("thread_ts", None)
        if slack_user_id is None or slack_channel is None or thread_ts is None:
            raise Exception("Slack user ID, channel, and thread timestamp are required to respond to a data question in Slack.")

        # Get the user's email address from their Slack profile, so we can find their account.
        slack_user_info = slack.get_user_info(slack_user_id=slack_user_id, slack_credential=slack_credential)
        if slack_user_info is None:
            raise Exception(f"Could not find Slack user profile for user ID { slack_user_id }.")
        slack_user_email = slack_user_info.get("profile", {}).get("email", None)

        user = User.objects.filter(email=slack_user_email).first()
        if user is None:
            raise Exception(f"Could not find user with email address { slack_user_email }.")
        
        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, text="Interpreting question...", thread_ts=thread_ts)

        question_search_terms = question.split(" ")
        question_search_terms = [term for term in question_search_terms if len(term) > 3]
        # Lowercase, remove special characters, and remove duplicates
        question_search_terms = list(set(question_search_terms))
        question_search_terms = [re.sub(r"[^a-zA-Z0-9]", "", term).lower() for term in question_search_terms]

        # FLOW: FIND VIZ ON TABLEAU NEXT/CORE #
        # ----------------------------------- #

        # Find Views (Tableau Cloud) or Visualizations (Tableau Next) that may answer the question. Start with Tableau Next. But first, yeah, determine whether both apply.
        use_tableau_core = True
        use_tableau_next = True

        keywords_no_tableau_core = ["no tableau cloud", "only tableau next", "only on tableau next", "only with tableau next", "not on tableau cloud", "not with tableau cloud", "tableau next only"]
        keywords_no_tableau_next = ["no tableau next", "only tableau cloud", "only on tableau cloud", "only with tableau cloud", "not on tableau next", "not with tableau next", "tableau cloud only"]
        for keyword in keywords_no_tableau_core:
            if keyword in question.lower():
                use_tableau_core = False
                log_and_display_message(f"Tableau Core is not applicable: \"{keyword}\" was specified.")
                break
        for keyword in keywords_no_tableau_next:
            if keyword in question.lower():
                use_tableau_next = False
                log_and_display_message(f"Tableau Next is not applicable: \"{keyword}\" was specified.")
                break

        # We will collect stuff in this list
        visualizations_for_review = []

        # Connect, Tableau Next
        if use_tableau_next:
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text="Connecting to Tableau Next...")
            try:
                connection_dict = tableau_next_api.connect()
            except Exception as e:
                log_and_display_message(f"Error connecting to Tableau Next: {e}")
                slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: There was a problem connecting to Tableau Next: {e}", thread_ts=thread_ts, icon_emoji=":cry:")
                use_tableau_next = False

        if use_tableau_next: # _Still_ using Tableau Next i.e. no issue connecting?
            # Our search will consist of finding the right Dashboard. To identify the right Dashboard, we need to consider the Visualizations on there, and in turn, the fields in the Visualizations.
            # The relations go as follows: AnalyticsDashboard (needs SOQL) -> AnalyticsDashboardWidget (needs SOQL) -> AnalyticsVizWidgetDef (needs SOQL) -> AnalyticsVisualization (REST API, includes fields).

            # Find AnalyticsDashboard, AnalyticsDashboardWidget, AnalyticsVizWidgetDef with SOQL
            dashboards_on_tn = tableau_next_api.get_entities_through_soql(connection=connection_dict, entity_type="AnalyticsDashboard")
            log_and_display_message(f"Found { len(dashboards_on_tn) } Dashboards on Tableau Next.")
            dashboard_widgets_on_tn = tableau_next_api.get_entities_through_soql(connection=connection_dict, entity_type="AnalyticsDashboardWidget")
            log_and_display_message(f"Found { len(dashboard_widgets_on_tn) } Dashboard Widgets on Tableau Next.")
            viz_widget_defs_on_tn = tableau_next_api.get_entities_through_soql(connection=connection_dict, entity_type="AnalyticsVizWidgetDef")
            log_and_display_message(f"Found { len(viz_widget_defs_on_tn) } Visualization Widget Definitions on Tableau Next.")

            # Find Visualizations
            log_and_display_message(f"Finding Visualizations on Tableau Next")
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text="Finding Visualizations on Tableau Next...")
            all_visualizations_collection = tableau_next_api.get_visualization_collection(connection_dict)
            log_and_display_message(f"Found { len(all_visualizations_collection) } Visualizations on Tableau Next.")

            # Reconcile the data from Dashboard all the way down to viz and field. At the end of the day, we're just going to add a list of vizzes (labels), and a list of fields (fieldNames), to each dashboard.
            for dashboard in dashboards_on_tn:
                dashboard_widgets = [widget for widget in dashboard_widgets_on_tn if widget.get("AnalyticsDashboardId") == dashboard.get("Id") and widget.get("Type") == "visualization"]
                for widget in dashboard_widgets:
                    viz_widget_defs = [defn for defn in viz_widget_defs_on_tn if defn.get("AnalyticsDashboardWidgetId") == widget.get("Id")]
                    for defn in viz_widget_defs:
                        dashboard_vizzes = [viz for viz in all_visualizations_collection if viz.get("id") == defn.get("AnalyticsVisualizationId")] # Here id is lowercase because it comes from  the REST API
                        # This is info we add. Fields is also in here already.
                        dashboard["visualizations"] = dashboard_vizzes

            # Keep a copy of this data with just the info we want to pass to OpenAI for review: IDs and names (labels) of the dashboards and visualizations, and their fields' names.
            # Add Tableau next dashboards' core info (dashboard, visualization, fields) to visualizations_for_review
            for dashboard in dashboards_on_tn:
                dashboard_info = {
                    "id": dashboard.get("Id"),
                    "label": dashboard.get("MasterLabel"),
                    "source": "tableau_next",
                    "visualizations": [viz.get("label") for viz in dashboard.get("visualizations", [])],
                    "fields": [viz.get("fields", ["Nope"])[field].get("fieldName") for viz in dashboard.get("visualizations", []) for field in viz.get("fields", [])]
                }
                visualizations_for_review.append(dashboard_info)

            log_and_display_message(f"Found visualizations for review from Tableau Next: { len(visualizations_for_review) }")

        if use_tableau_core:
            log_and_display_message("Getting Metadata API information from Tableau (\"Core\")")
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text="Connecting to Tableau...")
            try:
                tableau_core_connection_dict = tableau_rest_api.connect()
            except Exception as e:
                log_and_display_message(f"Error connecting to Tableau: {e}")
                slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: There was a problem connecting to Tableau: {e}", thread_ts=thread_ts, icon_emoji=":cry:")
                use_tableau_core = False

        if use_tableau_core: # _Still_ using Tableau Core i.e. no issue connecting?

            metadata_api_query = next((maq for maq in tableau_metadata_api.metadata_api_queries if maq.get("query_name", "?") == "dashboardsSheetsAndFields"), None)
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text="Finding visualizations on Tableau...")
            dashboards_sheets_and_fields = tableau_metadata_api.query_metadata_api_paginated(rest_api_connection=tableau_core_connection_dict, raw_query=metadata_api_query["query_contents"])

            for dashboard in dashboards_sheets_and_fields:
                dashboard_info = {
                    "id": dashboard.get("luid"),
                    "label": dashboard.get("name"),
                    "source": "tableau_core",
                    "visualizations": [sheet.get("name") for sheet in dashboard.get("sheets", [])],
                    "fields": [field.get("name") for sheet in dashboard.get("sheets", []) for field in sheet.get("sheetFieldInstances", [])]
                }
                visualizations_for_review.append(dashboard_info)

            log_and_display_message(f"Found visualizations for review from Tableau Core: { len(dashboards_sheets_and_fields) }")

        # FLOW: SELECT VIZ WITH OPENAI API #
        # -------------------------------- #

        # Check these with OpenAI, providing the question we are looking to answer for context.
        user_prompt = f"""
            Question: { question }\n\n
            Visualizations:\n\n
            ```json\n
            { json.dumps(visualizations_for_review, indent=4) }
            ```\n
        """

        class VizEvaluationResponse(BaseModel):
            id: str

        try:
            log_and_display_message(f"Sending vizzes to OpenAI to select the most adequate one.")
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text="Reviewing Visualizations to find the most suitable candidate...")
            openai_response = openai.openai_api_chat_completion(user_prompt=user_prompt, system_prompt=ai_prompts.tableau_next_question.system_prompt, user=None, response_format=VizEvaluationResponse)
        except Exception as e:
            error_message = f"There was a problem sending the prompt to OpenAI: {e}\n{traceback.format_exc()}"
            log_and_display_message(error_message, level="error")
            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message
            return

        if not hasattr(openai_response, "id") or openai_response.id is None or openai_response.id == "" or openai_response.id == "null":
            error_message = f"OpenAI response is missing 'id': {openai_response}"
            log_and_display_message(error_message, level="error")
            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message
            return

        selected_viz_id = openai_response.id
        selected_viz = next((viz for viz in visualizations_for_review if viz.get("id") == selected_viz_id), None)
        target_platform = selected_viz.get("source", "unknown platform") if selected_viz is not None else "unknown platform"
        log_and_display_message(f"OpenAI selected visualization ID { openai_response.id } on { target_platform }.")

        # FLOW: GET VIZ IMAGE FROM TABLEAU NEXT or CORE #
        # --------------------------------------------- #

        if target_platform == "tableau_next":
            # Re-get the viz (dashboard) on Next
            # selected_viz_tableau_next = tableau_next_api.get_visualization(connection_dict, asset_id_or_name=selected_viz.get("id"))
            # Except we don't need to use the API, we have this data already in dashboards_on_tn
            selected_viz_tableau_next = next((viz for viz in dashboards_on_tn if viz.get("Id") == selected_viz.get("id")), {})

            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text=f"Found the one we need! Getting details for \"{ selected_viz_tableau_next.get('MasterLabel', '?') }\" on Tableau Next\"...")

            viz_image_download_response = tableau_next_api.post_image_download(connection_dict, asset=selected_viz_tableau_next, metadata_only=False)
            viz_image_bytes = viz_image_download_response.content

        elif target_platform == "tableau_core":
            selected_viz_tableau_core = next((viz for viz in dashboards_sheets_and_fields if viz.get("luid") == selected_viz.get("id")), {})
            viz_image_download_response = tableau_rest_api.download_view_image(rest_api_connection=tableau_core_connection_dict, view_luid=selected_viz_tableau_core.get("luid"))
            viz_image_bytes = viz_image_download_response.content
        
        status_message = slack.post_status_message(slack_channel=slack_channel, 
        slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message

        message = f":chart_with_upwards_trend: This chart should help us answer the question!"
        slack.upload_file(slack_channel=slack_channel, slack_credential=slack_credential, file=viz_image_bytes, file_format="png", file_title="viz_image", initial_comment=message, thread_ts=thread_ts)

        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, text="Formulating an answer to the question...", thread_ts=thread_ts)

        # FLOW: GIVE IMAGE TO OPENAI TO ANSWER THE Q #
        # ------------------------------------------ #

        # Send image to OpenAI with question, ask for an explanation.
        openai_viz_comments = openai.comment_on_dashboard_file(file_bytes=viz_image_bytes, file_format="png", custom_prompt=f"Answer the following data question with the attached dashboard:\n\n{ question }")
        log_and_display_message(f"OpenAI Dashboard Comments: { openai_viz_comments }", level="info")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=openai_viz_comments, thread_ts=thread_ts)
        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message

        # FLOW: REBUILD VIZ IN TABLEAU NEXT #
        # --------------------------------- #

        # If we answered with Tableau Core, and we know we have the same Semantic Model on Tableau Next... why not try and rebuild the same viz over there? We will suggest to the user that this is possible, and it is up to them to trigger the action if desired.

        if target_platform == "tableau_core":

            selected_core_viz_luid = selected_viz_tableau_core.get("luid", None)

            message_blocks_for_rebuild = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "One more thing... We just answered this question with a viz on Tableau Cloud. Would you like to automatically rebuild it on Tableau Next? If the right data is available in Data Cloud, I can do that automatically for you!"
                    }
                },
                {
                    "type": "actions",
                    "block_id": "action_block_for_rebuild",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Let's try that!"
                            },
                            "style": "primary",
                            "value": f"{ selected_core_viz_luid }", # We only need to pass the selected viz LUID, no other context is needed here.
                            "action_id": "rebuild_core_viz_in_next"
                        }
                    ]
                }
            ]

            message_for_response = FormattedMessage("Would you like to rebuild this viz on Tableau Next?").for_slack()

            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, blocks=message_blocks_for_rebuild, text=message_for_response, thread_ts=thread_ts)

        return

    else:
        raise Exception(f"Source { source } is not supported yet. Only Slack is supported for now.")
    
def rebuild_core_viz_in_next(core_viz_luid:str, kwargs:dict) -> None:
    """
    Take an existing viz in Tableau Core, identify its data source, and if the data is available in Tableau Next, attempt to rebuild the viz there.
    """

    # Kwargs for where we need to respond, and the user ID
    slack_credential = SlackCredential.objects.first()
    slack_channel = kwargs.get("slack_channel", None)
    thread_ts = kwargs.get("thread_ts", None)
    action_message_ts = kwargs.get("action_message_ts", None)
    slack_user_id = kwargs.get("slack_user_id", None)

    # A message with a "Try again" button in case we run into an error and want to... try again.

    message_blocks_for_rebuild_try_again = [
        {
            "type": "actions",
            "block_id": "action_block_for_rebuild",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Try again?"
                    },
                    "style": "danger",
                    "value": f"{ core_viz_luid }", # We only need to pass the selected viz LUID, no other context is needed here.
                    "action_id": "rebuild_core_viz_in_next"
                }
            ]
        }
    ]

    # REBUILD Step 1: Use the Core Metadata API to identify which data source we'll be looking for #
    # Replace the original message in Slack first, to keep things tidy.
    slack.update_message(slack_channel=slack_channel, slack_credential=slack_credential, text=":zap: Okay! Working on rebuilding the viz on Tableau Next...", thread_ts=action_message_ts)
    # Update status
    status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, text="Let's do it! Looking up which data source is used by this viz on Tableau.", thread_ts=thread_ts)

    try:
        tableau_core_connection_dict = tableau_rest_api.connect()
    except Exception as e:
        error_message = f"Error connecting to Tableau: {e}"
        log_and_display_message(error_message, level="error")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, blocks=message_blocks_for_rebuild_try_again, text="Try again?", thread_ts=thread_ts)
        return
    
    try:
        viz_datasources_query = next((maq for maq in tableau_metadata_api.metadata_api_queries if maq.get("query_name", "?") == "dashboardsAndDataSources"), None)
        viz_datasources_response = tableau_metadata_api.query_metadata_api_paginated(rest_api_connection=tableau_core_connection_dict, raw_query=viz_datasources_query["query_contents"], mda_filter={"luid": core_viz_luid})
    except Exception as e:
        error_message = f"Error query the Tableau Metadata API to find the data source for the original viz: {e}"
        log_and_display_message(error_message, level="error")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, blocks=message_blocks_for_rebuild_try_again, text="Try again?", thread_ts=thread_ts)
        return
    
    if len(viz_datasources_response) == 0:
        error_message = f"No data sources found for the original viz."
        log_and_display_message(error_message, level="error")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
        return

    # REBUILD Step 2: Check if the same Semantic Model exists on Tableau Next #
    status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text=f"Checking to see if there is a semantic model on Tableau Next matching the data source from the original Tableau viz...")
    
    connection_dict = tableau_next_api.connect()
    
    all_semantic_models = tableau_next_api.get_all_semantic_models(connection_dict).get("items", [])

    tableau_next_matching_semantic_model = None
    if len(viz_datasources_response) > 0:
        tableau_core_viz_metadata = viz_datasources_response[0] # It is probably the first and only viz
        if len(tableau_core_viz_metadata.get("upstreamDatasources", [])) > 0:
            tableau_core_datasource_metadata = tableau_core_viz_metadata["upstreamDatasources"][0] # We take the first data source for now, further matching can take place later if we need to.
            tableau_next_matching_semantic_model = next((model for model in all_semantic_models if model.get("label", "!") == tableau_core_datasource_metadata.get("name", "?")), None)
            tableau_core_source_workbook = tableau_core_viz_metadata.get("workbook", {})

    if tableau_next_matching_semantic_model is None:
        error_message = f"Never mind, did not find the data we were looking for. Sorry!"
        log_and_display_message(error_message, level="error")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: {error_message}", thread_ts=thread_ts)
        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message
        return

    # We found a matching Semantic Model. We'll get the metadata right away so we can compare that to the workbook and fill that in our Next Visualization template.
    semantic_model_metadata = tableau_next_api.get_semantic_model_metadata(connection_dict=connection_dict, semantic_data_model=tableau_next_matching_semantic_model)
    semantic_model_data_objects = semantic_model_metadata.get("semanticDataObjects", [])
    semantic_model_data_object = semantic_model_data_objects[0] # If this fails, we can drop out anyway
    # For convenience, we'll created a combined list of dimensions and measures
    semantic_model_data_object_fields = semantic_model_data_object.get("semanticDimensions", []) + semantic_model_data_object.get("semanticMeasurements", [])

    # REBUILD Step 3: Get the existing workbook from Tableau Core #
    status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text=f"Getting the viz from Tableau Core, so we can dissect it...")

    # Before that, we'll also need to re-retrieve the Metadata API context we used to answer the question, specifically the sheet and fields available (which is used to determine what exactly we'll rebuild from the workbook)
    try:
        metadata_api_query = next((maq for maq in tableau_metadata_api.metadata_api_queries if maq.get("query_name", "?") == "dashboardsSheetsAndFields"), None)
        dashboards_sheets_and_fields_filtered = tableau_metadata_api.query_metadata_api_paginated(rest_api_connection=tableau_core_connection_dict, raw_query=metadata_api_query["query_contents"], mda_filter={"luid": core_viz_luid})
        selected_viz_tableau_core = dashboards_sheets_and_fields_filtered[0] # This _should_ be it, otherwise we didn't manage to retrieve the same match.
    except Exception as e:
        error_message = f"Failed to retrieve the original dashboard's sheets and fields: {e}"
        log_and_display_message(error_message, level="error")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: {error_message}", thread_ts=thread_ts)
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, blocks=message_blocks_for_rebuild_try_again, text="Try again?", thread_ts=thread_ts)
        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message
        return

    # Download the Tableau Core twb, find the dashboard we selected earlier, and determine basics such as rows, columns, color. Assume a single sheet for now.
    tableau_core_workbook = tableau_rest_api.download_file(rest_api_connection=tableau_core_connection_dict, asset_type="workbooks", luid=tableau_core_source_workbook.get("luid", ""), format="no_extract")
    tableau_core_workbook_content = tableau_core_workbook.content
    tableau_core_workbook_filename = tableau_core_workbook.headers.get("Content-Disposition", "attachment; filename=unknown.twb").split("filename=")[1].strip('"')
    
    if tableau_core_workbook_filename.endswith(".twbx"):
        tableau_core_workbook_twb_name, tableau_core_workbook_content = tableau_documents.get_txx_from_txxx(txxx_file=tableau_core_workbook_content, txxx_file_name=tableau_core_workbook_filename)
    else:
        print(1) # TODO

    tableau_core_workbook_tree = ET.ElementTree(ET.fromstring(tableau_core_workbook_content))

    # Find the worksheet that was used to answer the question, in the XML. We know that selected_viz_tableau_core contains the dashboard used to answer the question, so we'll first find the dashboard.
    try:
        # Let's just pick the first sheet on the dashboard used to answer the question, assuming that this is the one we want. Can be improved when we're no longer in "demo mode".
        # There's also a try-catch for now, that will simply pull us out if we're not finding what we need.
        tableau_core_dashboard_worksheets = tableau_core_workbook_tree.findall(".//worksheet")
        selected_worksheet_elem = [w for w in tableau_core_dashboard_worksheets if w.attrib.get("name", "!").lower() == selected_viz_tableau_core["sheets"][0].get("name", "?").lower()][0]

        # Now, dissect our worksheet. We are not going to look at the data source, and assume it's the one we need it to be. We are going to look for rows, columns, marks, etc. and find out what fields are being used on those.
        # At the end, we need a) the full list of fields (these will become the "fields" in Next) and b) how they are used (this will go into viewSpecification and visualSpecification).
        # And the best thing is, we're going to fill those things in in the template (sheet_definition) _as we go_.

        sheet_definition = copy.deepcopy(tableau_next_templates.visualization_template)
        # sheet_definition = copy.deepcopy(visualization_template)
        # Wire up the data source
        sheet_definition["dataSource"]["id"] = semantic_model_data_object.get("id", "")
        sheet_definition["dataSource"]["name"] = semantic_model_data_object.get("apiName", "")
        sheet_definition["dataSource"]["type"] = "SemanticModel"

        fields_counter = 0 # Used because we need dict keys F1, F2, etc.

        # Rows
        sheet_definition, fields_counter = tableau_next_functions.process_rows_or_cols_into_definition(sheet_definition, fields_counter, selected_worksheet_elem, "rows", semantic_model_data_object)

        # Columns
        sheet_definition, fields_counter = tableau_next_functions.process_rows_or_cols_into_definition(sheet_definition, fields_counter, selected_worksheet_elem, "cols", semantic_model_data_object)

        # Marks
        # Very basic for now; we have not yet processed any logic in case fields are used on marks; just the viz type and the single color (without field)
        sheet_definition, fields_counter = tableau_next_functions.process_marks_into_definition(sheet_definition, fields_counter, selected_worksheet_elem, semantic_model_data_object)

        # Filters
        sheet_definition, fields_counter = tableau_next_functions.process_filters_into_definition(sheet_definition, fields_counter, selected_worksheet_elem, semantic_model_data_object)

        # Other properties
        # There are a bunch of other properties we can transfer, some of which are in the window definition of the worksheet, so we pass the full xml to this function.
        sheet_definition, fields_counter = tableau_next_functions.process_other_into_definition(sheet_definition, fields_counter, selected_worksheet_elem, tableau_core_workbook_tree, semantic_model_data_object)

        # REBUILD Step 4b: add workspace
        workspaces = tableau_next_api.list_workspaces(connection_dict)
        log_and_display_message(f"Found { len(workspaces) } workspaces on Tableau Next.")

        workspace_name_for_demo = settings.TNQ_TEMP_WORKSPACE_NAME
        workspace_for_demo = next((ws for ws in workspaces if ws.get("name", "").lower() == workspace_name_for_demo.lower()), None)

        sheet_definition["workspace"] = {
            "name": workspace_for_demo.get("name", None)
        }

        new_viz_name = f"{ selected_viz_tableau_core.get('name', 'Unknown Name') } [From Tableau Core]"

        sheet_definition["label"] = new_viz_name
        sheet_definition["view"]["label"] = sheet_definition["label"]
        sheet_definition["name"] = new_viz_name.replace(" ", "_").replace("[", "").replace("]", "").lower() # Can be improved later

        # REBUILD Step 5: post
        tableau_next_new_viz = tableau_next_api.post_visualization(connection_dict=connection_dict, visualization_definition=sheet_definition)

        new_viz_message = f"Ready! Check out :tableaunext: <{ connection_dict['instance_url'] }/tableau/visualization/{ tableau_next_new_viz.get('name') }/edit|**{ tableau_next_new_viz.get('label', '?') }**>"
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=new_viz_message, thread_ts=thread_ts)
        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message
        
        return

    except Exception as e:
        error_message = f"We did not manage to rebuild the viz in Tableau Next, for \"technical reasons\":\n{e}\n{traceback.format_exc()}"
        log_and_display_message(error_message, level="error")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: {error_message}", thread_ts=thread_ts)
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, blocks=message_blocks_for_rebuild_try_again, text="Try again?", thread_ts=thread_ts)
        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message
        return

    return

