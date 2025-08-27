# imports - Python/general
import traceback
import re, json, random, io, copy
import xml.etree.ElementTree as ET
import pandas
from pydantic import BaseModel
from typing import Optional

# imports - Django
from django.contrib.auth import get_user_model
from django.conf import settings
User = get_user_model()

# imports - Orbit One
# Models and Classes
from core.models import SlackCredential, DataQuestion, DataQuestionAnswer
# Functions
from tableau_next_question.functions import log_and_display_message
# import core.functions.helpers_orbit_one as helpers_orbit_one
import core.functions.openai as openai
import core.functions.slack as slack
# import core.functions.entity_search as entity_search
# import core.functions.tableau.vizql_data_service as vizql_data_service
from core.functions.helpers import FormattedMessage
from core.functions.helpers_other import remove_fields_from_dictionary
import core.functions.prompts as ai_prompts
import core.functions.tableau.next_api as tableau_next_api
import core.functions.tableau.next_functions as tableau_next_functions
import core.functions.tableau.metadata_api as tableau_metadata_api
import core.functions.tableau.rest_api as tableau_rest_api
import core.functions.tableau.documents as tableau_documents

def respond_to_data_question(source:str, question:str, kwargs:dict) -> None:

    """
    Respond to a data question from a user in "Slack", "Teams", or "Google Chat" (those are also the respective values allowed for `source`). Note that currently only Slack is supported.
    
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

        # Get the user's email address from their Slack profile, so we can find their Orbit One ID.
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

        # Find Views (Tableau Cloud) or Visualizations (Tableau Next) that may answer the question. Start with Tableau Next. But first, yeah, determine whether both apply.
        use_tableau_core = True
        use_tableau_next = True

        keywords_no_tableau_core = ["no tableau cloud", "only tableau next", "only on tableau next", "not on tableau cloud"]
        keywords_no_tableau_next = ["no tableau next", "only tableau cloud", "only on tableau cloud", "not on tableau next"]
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

        if target_platform == "tableau_next":
            # Re-get the viz (dashboard) on Next
            # selected_viz_tableau_next = tableau_next_api.get_visualization(connection_dict, asset_id_or_name=selected_viz.get("id"))
            # Except we don't need to use the API, we have this data already in dashboards_on_tn
            selected_viz_tableau_next = next((viz for viz in dashboards_on_tn if viz.get("Id") == selected_viz.get("id")), {})

            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text=f"Found the one we need! Getting details for \"{ selected_viz_tableau_next.get('MasterLabel', '?') }\" on Tableau Next\"...")

            viz_image_download = tableau_next_api.post_image_download(connection_dict, asset=selected_viz_tableau_next, metadata_only=False)

        elif target_platform == "tableau_core":
            selected_viz_tableau_core = next((viz for viz in dashboards_sheets_and_fields if viz.get("luid") == selected_viz.get("id")), {})
            viz_image_download = tableau_rest_api.download_view_image(rest_api_connection=tableau_core_connection_dict, view_luid=selected_viz_tableau_core.get("luid"))

            viz_image_bytes = viz_image_download.content
            message = f":chart_with_upwards_trend: This chart should help us answer the question!"
            slack.upload_file(slack_channel=slack_channel, slack_credential=slack_credential, file=viz_image_bytes, file_format="png", file_title="viz_image", initial_comment=message, thread_ts=thread_ts)
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message

        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, text="Formulating an answer to the question...", thread_ts=thread_ts)

        # Send image to OpenAI with question, ask for an explanation.
        openai_viz_comments = openai.comment_on_dashboard_file(file_bytes=viz_image_bytes, file_format="png", custom_prompt=f"Answer the following data question with the attached dashboard:\n\n{ question }")
        log_and_display_message(f"OpenAI Dashboard Comments: { openai_viz_comments }", level="info")
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=openai_viz_comments, thread_ts=thread_ts)
        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message


        # If we answered with Tableau Core, and we know we have the same Semantic Model on Tableau Next... why not try and rebuild the same viz over there?

        if target_platform == "tableau_core":
            
            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, text="I have an idea! One moment, checking existing Semantic Models on Tableau Next...", thread_ts=thread_ts)

            all_semantic_models = tableau_next_api.get_all_semantic_models(connection_dict).get("items", [])

            status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None), text=f"Checking to see if there is one matching the data from the Tableau viz we just used earlier...")

            viz_luid = selected_viz_tableau_core.get("luid", None)
            viz_datasources_query = next((maq for maq in tableau_metadata_api.metadata_api_queries if maq.get("query_name", "?") == "dashboardsAndDataSources"), None)
            viz_datasources_response = tableau_metadata_api.query_metadata_api_paginated(rest_api_connection=tableau_core_connection_dict, raw_query=viz_datasources_query["query_contents"], mda_filter={"luid": viz_luid})

            tableau_next_matching_semantic_model = None
            if len(viz_datasources_response) > 0:
                tableau_core_viz_metadata = viz_datasources_response[0] # It is probably the first and only viz
                if len(tableau_core_viz_metadata.get("upstreamDatasources", [])) > 0:
                    tableau_core_datasource_metadata = tableau_core_viz_metadata["upstreamDatasources"][0] # We take the first data source for now, further matching can take place later if we need to.
                    tableau_next_matching_semantic_model = next((model for model in all_semantic_models if model.get("label", "!") == tableau_core_datasource_metadata.get("name", "?")), None)
                    tableau_core_source_workbook = tableau_core_viz_metadata.get("workbook", {})

            if tableau_next_matching_semantic_model is None:
                slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text="Never mind, did not find the data we were looking for.", thread_ts=thread_ts)
                status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message

            # We found a matching Semantic Model, so let's rebuild the viz with it! First, let's get the workbook.

            # Download the Tableau Core twb, find the dashboard we selected earlier, and determine basics such as rows, columns, color. Assume a single sheet for now.
            tableau_core_workbook = tableau_rest_api.download_file(rest_api_connection=tableau_core_connection_dict, asset_type="workbooks", luid=tableau_core_source_workbook.get("luid", ""), format="no_extract")
            tableau_core_workbook_content = tableau_core_workbook.content
            tableau_core_workbook_filename = tableau_core_workbook.headers.get("Content-Disposition", "attachment; filename=unknown.twb").split("filename=")[1].strip('"')
            
            if tableau_core_workbook_filename.endswith(".twbx"):
                tableau_core_workbook_twb_name, tableau_core_workbook_content = tableau_documents.get_txx_from_txxx(txxx_file=tableau_core_workbook_content, txxx_file_name=tableau_core_workbook_filename)
            else:
                print(1) # TODO

            tableau_core_workbook_tree = ET.ElementTree(ET.fromstring(tableau_core_workbook_content))

            
            semantic_model_metadata = tableau_next_api.get_semantic_model_metadata(connection_dict=connection_dict, semantic_data_model=tableau_next_matching_semantic_model)

            
            # TODO: after that, match this against the fields (semanticDataObjects -> semanticDimensions + semanticMeasurements) to find the items we need.
            
            # TODO: after that, put together a new Visualization definition that recreates the sheet from above, and refers to the semantic model as well.


        return
    
        # Below are a few... experiments.

        workspaces = tableau_next_api.list_workspaces(connection_dict)
        log_and_display_message(f"Found { len(workspaces) } workspaces on Tableau Next.")

        workspace_name_for_demo = "Timothy_s_Workspace"

        workspace_for_demo = next((ws for ws in workspaces if ws.get("name", "").lower() == workspace_name_for_demo.lower()), None)

        assets_for_workspace = tableau_next_api.get_workspace_asset_collection(connection_dict, workspace_for_demo.get("id", None))

    
        semantic_models_for_workspace = [asset for asset in assets_for_workspace if asset.get("assetType", "") == "SemanticModel"]


        asset_id = next((asset.get("assetId", None) for asset in semantic_models_for_workspace), None)

        all_semantic_models = tableau_next_api.get_all_semantic_models(connection_dict).get("items", [])


        selected_semantic_model = all_semantic_models[0]
        selected_semantic_model_id = selected_semantic_model.get("id", None)


        # As a test, let's get a specific visualization, update an attribute, and create a copy.
        source_viz_name = "OG_Viz_To_Recreate"
        source_viz = tableau_next_api.get_visualization(connection_dict, asset_id_or_name=source_viz_name)
        target_viz = tableau_next_functions.copy_viz_with_changes(source_viz=source_viz, new_name="OG_Viz_Recreated", new_label="Copied Viz That Is Now Per Category")
        target_viz_on_next = tableau_next_api.post_visualization(connection_dict, target_viz)
        target_viz_on_next_url = f"{ settings.SF_ORG_DOMAIN }tableau/visualization/{ target_viz_on_next.get('name') }/edit"

        formatted_message_for_response = FormattedMessage(f"Here is a new viz on Tableau Next, it's now per category instead of sub-category!\n\n{ target_viz_on_next_url }").for_slack()

        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=formatted_message_for_response, thread_ts=thread_ts)

        return

        entities_for_answer = [{"name": "dummy"}]

        # TODO: actually do that.
        # TODO: filter on the user's permissions, so we only show them the entities they have access to.

        # PRELIMINARY RESULTS #
        #######################

        # Say we have n results
        preliminary_response_blocks = []
        preliminary_response_text = ""
        preliminary_message_intro = f":+1: Okay, I've looked at the data sources, tables, and views in the analytics Environments connected to Orbit One. At first glance, there are up to { len(entities_for_answer) } of those that could provide an answer to the questions. The most promising ones are:"
        preliminary_message_intro_section = { "type": "section", "text": { "type": "mrkdwn", "text": preliminary_message_intro } }
        preliminary_response_blocks.append(preliminary_message_intro_section)
        preliminary_response_text += preliminary_message_intro

        # Workspaces, just for illustration purposes
        preliminary_message_intro_ws_section = { "type": "section", "text": { "type": "mrkdwn", "text": f"By the way, these are the workspaces on your Tableau Next environment: { ', '.join([workspace.get('name', '<unknown name>') for workspace in workspaces]) }" } }
        preliminary_response_blocks.append(preliminary_message_intro_ws_section)

        # List the most promising ones (top 3)
        preliminary_message_promising_section = { "type": "section", "text": { "type": "mrkdwn", "text": "" } }
        for entity in entities_for_answer[:3]:

            # Properties
            entity_name = "<unknown name>"

            # Message
            preliminary_message_promising_entity = f"\n• *{ entity_name }* on { entity.get('entity_environment', {}).get('name', '<unknown environment>') }"
            preliminary_message_promising_section["text"]["text"] += preliminary_message_promising_entity
            preliminary_response_text += preliminary_message_promising_entity

        preliminary_response_blocks.append(preliminary_message_promising_section)

        preliminary_message_outro = f"\nAt this point, I'll do a double-take on the initial results and perform a more in-depth analysis to determine which of those are most likely to provide us with a great answer to your question. One moment, I'll get right back to you!"
        preliminary_message_outro_section = { "type": "section", "text": { "type": "mrkdwn", "text": preliminary_message_outro } }
        preliminary_response_blocks.append(preliminary_message_outro_section)
        preliminary_response_text += preliminary_message_outro

        preliminary_response_formatted = FormattedMessage(preliminary_response_text).for_slack()

        status_message = slack.post_status_message(slack_channel=slack_channel, slack_credential=slack_credential, previous_status_message_ts=status_message.get("ts", None)) # Delete status message

        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, blocks=preliminary_response_blocks, text=preliminary_response_formatted, thread_ts=thread_ts)

        # FINAL RESULTS #
        #################

        # Send info to OpenAI, but only what is relevant: the entities with their names, and fields. We pass the Entity ID as well, so we can ask for that to be provided in the response after which we can relate that back to our data.
        entities_for_review = []

        for entity in entities_for_answer:
            entity_for_review = {}
            entity_for_review["name"] = "<unknown name>"
            entity_for_review["id"] = "<unknown id>"
            entity_field_names = "field1|field2"
            if entity_field_names is not None:
                entity_for_review["field_names"] = entity_field_names.split("|")
            else:
                entity_for_review["field_names"] = []

            entities_for_review.append(entity_for_review)

        # Prepare our prompt and expected response format for OpenAI.
        
        user_prompt = f"""
            Question: { question }\n\n
            Data sets:\n\n
            ```json\n
            { json.dumps(entities_for_review, indent=4) }
            ```\n
        """
        class DataSetEvaluation(BaseModel):
            id: int
            name: str
            fields: list[str]
            reason: str
        class DataSetEvaluationResponse(BaseModel):
            explanation: str
            top_data_sets: list[DataSetEvaluation]
            
        try:
            log_and_display_message(f"Sending data question to OpenAI.")
            openai_response = openai.openai_api_chat_completion(user_prompt=user_prompt, system_prompt=ai_prompts.vds_select_datasources.system_prompt, user=None, response_format=DataSetEvaluationResponse)
        except Exception as e:
            error_message = f"There was a problem sending the data question to OpenAI: {e}\n{traceback.format_exc()}"
            log_and_display_message(error_message, level="error")
            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
        
        else:
        
            response_blocks = []
            intro_text = f":wave: Hi again { first_name }! After a thorough review of the candidate data sets, here is where we stand:\n\n{ openai_response.explanation }\n\nWith that in mind, here are the top 5 data sets that are most likely to provide an answer to your question:\n\n"
            block_divider = {
                "type": "divider"
            }
            response_blocks.append(block_divider)
            block_intro = {
                "type": "section",
                "text": { 
                    "type": "mrkdwn",
                    "text": intro_text
                }
            }
            response_blocks.append(block_intro)
            message_for_response = intro_text

            answer_button_labels = ["Answer with this data source", "Pick this one", "Sounds good, what's the answer?", "Answer with this one", "This one looks good", "This one is the best"]

            # Start collecting the top datasets as dicts so we can store them in the database as DataQuestion.
            top_data_sets_json = []

            try:
                data_question = DataQuestion(
                    question=question,
                    created_by=user,
                    top_data_sets=top_data_sets_json,
                )
                data_question.save()
                data_question_id = data_question.id
            except Exception as e:
                log_and_display_message(f"There was a problem saving the Data Question to the database: {e}\n{traceback.format_exc()}", level="error")

            for index, suggested_dataset in enumerate(openai_response.top_data_sets, start=1):

                block_divider = {
                    "type": "divider"
                }
                response_blocks.append(block_divider)
                message_for_response += f"\n-\n"

                entity_id = suggested_dataset.id
                entity = next((e for e in entities_for_answer if e.get("entity_object", {}).get("id", None) == entity_id), None)

                # Get the entity name, type and a few properties
                entity_name = "<unknown name>"
                entity_name_terms = entity_name.split(" ")
                entity_name_terms = [re.sub(r"[^a-zA-Z0-9]", "", term).lower() for term in entity_name_terms if len(term) > 3]
                entity_type = "<unknown type>"

                top_data_sets_json.append({
                    "id": entity_id,
                    "ooid": "<unknown ooid>",
                    "name": entity_name,
                    "fields": suggested_dataset.fields,
                    "reason": suggested_dataset.reason
                })

                message_for_response += f"\n{ entity_type } **{ entity_name }**"
                message_for_response += f"\n• Environment: { entity.get('entity_environment', {}).get('name', '<unknown environment>') }"

                block_header = {
                    "type": "header",
                    "text": { 
                        "type": "plain_text",
                        "text": f"{index}. { entity_name }"
                    }
                }
                response_blocks.append(block_header)

                section_details = {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• *Environment:* { entity.get('entity_environment', {}).get('name', '<unknown environment>') }\n• *Type:* { entity_type }"
                    }
                }
                response_blocks.append(section_details)

                section_reason = {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"> { suggested_dataset.reason }"
                    }
                }
                response_blocks.append(section_reason)

                # Put together the button to answer with this data source, with a random label.
                answer_button_label = random.choice(answer_button_labels)
                answer_button = {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": answer_button_label
                    },
                    "value": f"{ data_question_id }:{ entity_id }", # Naming convention is <data_question_id>:<entity_id>
                    "action_id": f"answer_im_data_question"
                }

                if suggested_dataset.fields is not None:
                    field_names_list_code = [f"`{ field_name }`" for field_name in suggested_dataset.fields]
                    field_fields = {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Relevant fields:* { ', '.join(field_names_list_code) }"
                        },
                        "accessory": answer_button
                    }
                    message_for_response += f"\nRelevant fields: { ', '.join(field_names_list_code) }"
                else:
                    field_fields = {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Relevant fields:* No fields found."
                        }
                    }
                    message_for_response += f"• *Relevant fields:* No fields found."

                response_blocks.append(field_fields)

            data_question.top_data_sets = top_data_sets_json
            data_question.save()

            formatted_message_for_response = FormattedMessage(message_for_response).for_slack()

            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, blocks=response_blocks, text=formatted_message_for_response, thread_ts=thread_ts)

    else:
        raise Exception(f"Source { source } is not supported yet. Only Slack is supported for now.")
    
def respond_to_data_question_part_deux(data_question_id:int, entity_id:int, kwargs:dict) -> None:
    """
    Respond to a data question from a user in "Slack", "Teams", or "Google Chat" (those are also the respective values allowed for source). 
    
    This is part two of the process, where we have already presented the user with a list of data sets to answer the question with, and now they have chosen one. This was stored as a DataQuestion object in the database, and now we need to process it.

    Answering the question takes place in a number of steps:
    1. Get the question
    2. Generate the query
    3. Get the data from the data source, with the query
    4. Generate a text response based on the data
    5. Generate a chart based on the data

    Kwargs is a dictionary containing additional information that may vary depending on the source. For example, in Slack, it may contain the user ID.
    """

    # 1. Get the question #
    # ------------------- #
    
    data_question = DataQuestion.objects.filter(id=data_question_id).first()
    if data_question is None:
        raise Exception(f"Data question with ID { data_question_id } not found.")
    
    selected_data_set = next((ds for ds in data_question.top_data_sets if ds.get("id", None) == entity_id), None)

        
    data_question_answer = DataQuestionAnswer(
        data_question=data_question,
        created_by=data_question.created_by, # For now; perhaps later, a question can be answered by someone else?
        with_data_set=selected_data_set, # This is the data set that was selected by the user.
    )
    data_question_answer.save()
    
    # Get the entity from the database
    entity = Entity.objects.filter(id=entity_id).first()
    if entity is None:
        error_message = f"Entity with ID { entity_id }, which was selected to answer the question, was not found."
        log_and_display_message(error_message, level="error")
        data_question_answer.errors = error_message
        data_question_answer.save()
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
        return
    
    # TODO: use the OOID instead of Entity ID for consistency in case it changed.

    # Kwargs for where we need to respond, and the user ID
    slack_channel = kwargs.get("slack_channel", None)
    thread_ts = kwargs.get("thread_ts", None)
    slack_user_id = kwargs.get("slack_user_id", None)
    
    # Get the user's email address from their Slack profile, so we can find their Orbit One ID.
    slack_credential = Organization.objects.first().organizationslackcredential_set.first()

    preliminary_response_blocks = []
    preliminary_response_text = ""

    block_divider = {
        "type": "divider"
    }
    preliminary_response_blocks.append(block_divider)
    preliminary_response_text += f"\n-\n"
    block_header = {
        "type": "header",
        "text": { 
            "type": "plain_text",
            "text": f"Answering question with \"{ entity.title() }\""
        }
    }
    preliminary_response_blocks.append(block_header)

    preliminary_message_intro = f":saluting_face: Okay, let's do it! We're going use the data set *{ entity.title() }* on { entity.environment.name } to answer the following question:\n\n> { data_question.question }\n\nBear with me as I formulate the right query, and get us the answer..."
    preliminary_message_intro_section = { "type": "section", "text": { "type": "mrkdwn", "text": preliminary_message_intro } }
    preliminary_response_blocks.append(preliminary_message_intro_section)
    preliminary_response_text += preliminary_message_intro
    
    # Just a quick post to say we're working on it.
    slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, blocks=preliminary_response_blocks, text=preliminary_response_text, thread_ts=thread_ts)

    # 2. Generate the query #
    # --------------------- #

    # Time to start generating the query to get the answer. This will differ depending on the type of entity we have. A Tableau Datasource will use the VizQL Data Service, while a Snowflake Relation will use the Snowflake API. A BigQuery Relation will use the BigQuery API, and so on.

    if entity.type == "Datasource":

        # If a Tableau Datasource, we'll get additional field information from the VizQL Data Service.
        vizql_data_service_response = vizql_data_service.read_metadata(user_to_impersonate=data_question.created_by, environment=entity.environment, datasource_luid=entity.rest_api_data.get("id"))
        # And from the Metadata API!
        metadata_api_fields = entity.metadata_api_data.get("fields", [])

        # We're going to combine these in a new list, that will contain a number of fields from both APIs. This list will be passed to the OpenAI API to form the query. From the VizQL Data Service list, we'll keep fields we need to put together the query (fieldCaption) and fields with interesting metadata (dataType). From the Metadata API, we are particularly interested in the role of the field (dimension/measure).

        fields_for_query = []
        for field in vizql_data_service_response.get("data", []):
            field_for_query = {}
            field_for_query["fieldCaption"] = field.get("fieldCaption", "<unknown>")
            field_for_query["dataType"] = field.get("dataType", "<unknown>")
            field_for_query["role"] = next((f.get("role") for f in metadata_api_fields if f.get("name") == field.get("fieldCaption")), None)
            fields_for_query.append(field_for_query)
        
        # Now we have a list of fields that we can use to generate the query. We need to pass this to OpenAI, along with the question and the entity name.
        user_prompt = f"""
            Question: { data_question.question }\n\n
            Fields:\n\n
            ```json\n
            { json.dumps(fields_for_query, indent=4) }
            ```\n
        """

        class VizQLDataServiceField(BaseModel):
            fieldCaption: str
            sortPriority: Optional[int]
            sortDirection: Optional[str]
            function: Optional[str]
        class FieldRef(BaseModel):
            fieldCaption: str
        class VizQLDataServiceFilter(BaseModel):
            field: FieldRef
            filterType: str
            values: list[str]
            exclude: bool
        class VizQLDataServiceQuery(BaseModel):
            fields: list[VizQLDataServiceField]
            filters: list[VizQLDataServiceFilter]

        try:
            log_and_display_message(f"Sending data to OpenAI to generate VizQL Data Service Query.")
            openai_response = openai.openai_api_chat_completion(user_prompt=user_prompt, system_prompt=ai_prompts.vds_nlq_to_vds.system_prompt, user=None, response_format=VizQLDataServiceQuery)
        except Exception as e:
            error_message = f"There was a problem getting a VizQL Data Service Query from OpenAI: {e}"
            log_and_display_message(f"{ error_message }\n{traceback.format_exc()}", level="error")
            data_question_answer.errors = error_message
            data_question_answer.save()
            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
            return
    
        # Convert the OpenAI response to JSON.
        vizql_data_service_query = openai_response.dict()

        # Minor fixes to the query:
        # If OpenAI has omitted an attribute (e.g. no function for a dimension), it will have specified None. We need to remove that from the query.
        for field in vizql_data_service_query.get("fields", []):
            if field.get("function") is None:
                field.pop("function")
            if field.get("sortPriority") is None:
                field.pop("sortPriority")
            if field.get("sortDirection") is None:
                field.pop("sortDirection")
        # If OpenAI has specified the same sortPriority for multiple fields, we need to remove the sortPriority from all but the first field.
        sort_priority_seen = set()
        for field in vizql_data_service_query.get("fields", []):
            if field.get("sortPriority") is not None:
                if field.get("sortPriority") in sort_priority_seen:
                    field.pop("sortPriority")
                    field.pop("sortDirection", None)  # Remove sortDirection if sortPriority is removed
                else:
                    sort_priority_seen.add(field.get("sortPriority"))

        # For clarity in Slack, we'll list the fields and filters in the query in a more readable format.
        fields_list = []
        for field in vizql_data_service_query.get("fields", []):
            field_list_item = f"{ field.get('fieldCaption', '<unknown>') }"
            if field.get("function") is not None:
                field_list_item += f" ({ field.get('function') })"
            fields_list.append(f"`{ field_list_item}`")
        fields_list = ", ".join(fields_list)
        filters_list = []
        for filter in vizql_data_service_query.get("filters", []):
            filter_list_item = f"{ filter.get('field', {}).get('fieldCaption', '<unknown>') }"
            if filter.get("filterType") is not None:
                filter_list_item += f" ({ filter.get('filterType') })"
            if filter.get("values") is not None:
                filter_list_item += f" ({ ', '.join(filter.get('values')) })"
            filters_list.append(f"`{ filter_list_item }`")

        # Aside from that, we will still upload the JSON file to the Slack message, so the user can see the full query. We'll use io.BytesIO here.
        query_json_file = io.BytesIO()
        query_json_file.write(json.dumps(vizql_data_service_query, indent=4).encode("utf-8"))
        query_json_file.seek(0)

        # Log/present the query to the user in slack, so they can see what we're going to do.
        message = f":technologist: Okay, I've put together a query to get the answer to your question. Here it is:\n\nFields: { fields_list }\n\n"
        if len(filters_list) > 0:
            message += f"Filters: { ', '.join(filters_list) }\n\n"
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=message, thread_ts=thread_ts)
        slack.upload_file(slack_channel=slack_channel, slack_credential=slack_credential, file=query_json_file, file_format="json", file_title="vizql_data_service_query", initial_comment="Here is the full query in JSON format, if you need to see it.", thread_ts=thread_ts)

        # 3. Get the data #
        # --------------- #

        try:
            vizql_data_service_response = vizql_data_service.query_datasource(user_to_impersonate=data_question.created_by, environment=entity.environment, datasource_luid=entity.rest_api_data.get("id"), query=vizql_data_service_query)

            data_for_answer = vizql_data_service_response.get("data", [])

            # Sometimes we tried to specify a filter that didn't work, and we get an empty result set. In that case, we will try again without the filter, after letting the user know.
            if len(data_for_answer) == 0 and len(vizql_data_service_query.get("filters", [])) > 0:
                slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=":exclamation: The query returned no results. This can happen if the filter we specified didn't work. Let's try again without the filter.", thread_ts=thread_ts)
                # Remove the filters from the query
                vizql_data_service_query.pop("filters")
                # Run the query again
                vizql_data_service_response = vizql_data_service.query_datasource(user_to_impersonate=data_question.created_by, environment=entity.environment, datasource_luid=entity.rest_api_data.get("id"), query=vizql_data_service_query)
                data_for_answer = vizql_data_service_response.get("data", [])

        except Exception as e:
            error_message = f"There was a problem getting the data from the VizQL Data Service: {e}"
            # TODO: pass this in a better format than string.
            if "400803" in str(e) and "invalid" in str(e).lower() and "filter" in str(e).lower():
                slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=":exclamation: The query returned no results. This can happen if the filter we specified didn't work. Let's try again without the filter.", thread_ts=thread_ts)
                try:
                    # Remove the filters from the query
                    vizql_data_service_query.pop("filters")
                    # Run the query again
                    vizql_data_service_response = vizql_data_service.query_datasource(user_to_impersonate=data_question.created_by, environment=entity.environment, datasource_luid=entity.rest_api_data.get("id"), query=vizql_data_service_query)
                    data_for_answer = vizql_data_service_response.get("data", [])
                except Exception as e:
                    error_message = f"There was a problem getting the data from the VizQL Data Service: {e}"
                    log_and_display_message(f"{ error_message }\n{traceback.format_exc()}", level="error")
                    data_question_answer.errors = error_message
                    data_question_answer.save()
                    slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
                    return
            else:
                log_and_display_message(f"{ error_message }\n{traceback.format_exc()}", level="error")
                data_question_answer.errors = error_message
                data_question_answer.save()
                slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
                return
            
        # Use pandas to convert the data to a markdown table for our Slack message.
        df = pandas.DataFrame(data_for_answer)
        # data_as_markdown_table = df.to_markdown(index=False, tablefmt="fancy_grid")
        # Nah, a CSV would be better here.
        data_as_csv = io.BytesIO()
        data_as_csv.write(df.to_csv(index=False).encode("utf-8"))
        data_as_csv.name = "data.csv"
        data_as_csv.seek(0)

        # Table format, in "code"
        # message = f":1234: We have our data! Here it is:\n\n```{ data_as_markdown_table }\n```"
        # slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=message, thread_ts=thread_ts)
        # CSV format
        message = f":1234: We have our data! Here it is:"
        slack.upload_file(slack_channel=slack_channel, slack_credential=slack_credential, file=data_as_csv, file_format="csv", file_title="data", initial_comment=message, thread_ts=thread_ts)

        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=":thinking_face: We're going to try and use that data to formulate an answer the to question. One moment...", thread_ts=thread_ts)

        # 4. Formulate a text answer #
        # -------------------------- #

        try:
            openai_response = openai.analyze_dataset(data=data_for_answer, question=data_question.question, user=data_question.created_by)
            message = f":bulb: Here is a possible answer to your question...\n\n { FormattedMessage(openai_response).for_slack() }"
            data_question_answer.answer_text = openai_response
            data_question_answer.save()
            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=message, thread_ts=thread_ts)
        except Exception as e:
            error_message = f"There was a problem getting the answer from OpenAI: {e}"
            log_and_display_message(f"{ error_message }\n{traceback.format_exc()}", level="error")
            data_question_answer.errors = error_message
            data_question_answer.save()
            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
            return
        
        slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=":coffee: Now let's visualize the data! Bear with me, this can take a while. Perhaps get a coffee or tea...", thread_ts=thread_ts)

        # 5. Draw a chart for the answer #
        # ------------------------------ #

        # We can use OpenAI Assistant to generate a chart based on the data. We need to pass the data to OpenAI, and ask it to generate a chart based on the data.

        system_prompt = """
        You are a Python data analyst. 
        
        You'll want to generate a chart based on the data provided. The chart should be relatively simple and it should answer the question asked by the user.
        """
        user_prompt = f"""
        Data: 
        ```json\n
        { json.dumps(data_for_answer, indent=4) }
        ```\n
        Create a chart best suited to answer the following question: { data_question.question }.
        """

        try:
            log_and_display_message(f"Sending data to OpenAI draw a chart.")
            chart_image = openai.data_to_chart_with_assistant(json_data=data_for_answer, user=None, system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception as e:
            error_message = f"There was a problem getting the chart image from OpenAI: {e}"
            log_and_display_message(f"{ error_message }\n{traceback.format_exc()}", level="error")
            data_question_answer.errors = error_message
            data_question_answer.save()
            slack.post_message(slack_channel=slack_channel, slack_credential=slack_credential, text=f":x: { error_message }", thread_ts=thread_ts, icon_emoji=":cry:")
            return

        # Post to Slack
        slack.upload_file(slack_channel=slack_channel,  slack_credential=slack_credential, file=chart_image, file_format="png", file_title=chart_image.name, initial_comment=":chart_with_upwards_trend: Here is a chart generated based on the data set you selected.", thread_ts=thread_ts)
