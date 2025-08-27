# imports - Python/general
import traceback
import requests, re, json

# imports - Django
# N/A

# imports - Orbit One
# Models
# N/A

# At least two functions here (parse_query_to_components and query_metadata_api_paginated) were copied from our Biztory tableau-tools repository (https://github.com/biztory/tableau-tools/blob/7bc15dda0065c04567c22df5af8a3b5a7963ef20/tableau-rls-finder/functions/metadata_api.py#L7)

# At the bottom of this file, we have a list of predefined metadata API queries.

def parse_query_to_components(raw_query:str):
    """
    Looks for a few different parts of the query and returns those as a dict, making some actions downstream easier.
    """
    # Replace multiple spaces, clear newlines, etc.
    try:
        query = re.sub(r"\s{2,}", " ", raw_query.replace("\n", "")).strip()
        query_name = re.match(r"query (\w+) {", query).groups()[0]
    except Exception as e:
        query_name = query[:query.find("{")].replace("query ", "")
        raise Exception(f"Something went wrong determining the name for this query.\n\t{e}\n\tGoing with the second guess \"{ query_name }\".")
    
    try:
        query_body = query[query.find("{"):]
        # Split the body in two, and between those two bits, we can insert the pagination stuff we need.
        query_root_part = query_body[:query_body.find("{", 1)]
        query_root_part_name = query_root_part.replace("{ ", "").replace(" ", "")
        query_not_root_part = query_body[query_body.find("{", 1):]
        query_components = {
            "name": query_name,
            "body": query_body,
            "root_part": query_root_part,
            "root_part_name": query_root_part_name,
            "not_root_part": query_not_root_part
        }
        return query_components
    except Exception as e:
        raise Exception(e)

def query_metadata_api_paginated(rest_api_connection:dict, raw_query:str, mda_filter:dict={}) -> list:
    """
    Receive a "generic" Metadata API query, and transform it into a parametrized query with pagination. 
    """

    page_size = 666

    query_components = parse_query_to_components(raw_query)

    # Formalities
    metadata_api_endpoint_url = rest_api_connection['tableau_url'] + "/api/metadata/graphql"

    has_next_page = True
    end_cursor = None
    pages_processed = 1
    results_processed = 0
    results = []

    # logger.info(f"Running query: { query_components['name'] }")

    while has_next_page:

        # logging.info(f"\tProcessing query with pagination, page { pages_processed }.")
        # Manipulate the query to include pagination logic
        # { root_part } (first: 666, after: <cursor>, orderBy: { field: ID, direction: ASC }) { not_root_part }
        # The first time, we won't have a cursor; afterwards, we will
        if end_cursor is not None:
            query_pagination_after_component = f", after: \"{ end_cursor }\""
        else:
            query_pagination_after_component = ""
        if mda_filter == {}:
            # No filter, just paginate
            query_pagination_component = f"(first: { page_size }{ query_pagination_after_component }, orderBy: {{ field: ID, direction: ASC }})"
        else:
            # Filter, we go for broke. Do note that the key has no quotes, the value does.
            query_pagination_component = f"(filter: {{ { list(mda_filter.keys())[0] }: \"{ list(mda_filter.values())[0] }\" }})"

        payload = {
            "query": f"query { query_components['name'] } { query_components['root_part'] }{ query_pagination_component }{ query_components['not_root_part'] }"
        }
        try:
            metadata_query_response = requests.post(url=metadata_api_endpoint_url, json=payload, headers=rest_api_connection["headers"])
            metadata_query_results = metadata_query_response.json()["data"][query_components["root_part_name"]]
        except Exception as e:
            raise Exception(f"Something went wrong querying the metadata API for query { query_components['name'] }.\n\t{e}The response was:{ metadata_query_response.text }")
        
        has_next_page = metadata_query_results.get("pageInfo", {}).get("hasNextPage", False)
        end_cursor = metadata_query_results.get("pageInfo", {}).get("endCursor", None)
        results_processed += page_size
        results += metadata_query_results.get("nodes", [])
        # logger.info(f"\tResults processed: { results_processed }")
        pages_processed += 1

    return results


metadata_api_queries = [
    { 
        "query_name": "publishedDatasourcesColumns",
        "query_contents": """
            query publishedDatasourcesColumns {
                publishedDatasourcesConnection {
                    nodes {
                    luid,
                        fields {
                            id,
                            name,
                            isHidden,
                            fullyQualifiedName,
                            __typename,
                            ... on ColumnField {
                                role,
                                aggregation
                            },
                            ... on CalculatedField {
                                role,
                                aggregation
                            },
                            ... on GroupField {
                                role
                            }
                        }
                    },
                    pageInfo {
                    hasNextPage,
                    endCursor
                    }
                }
            }
        """
    },
    { 
        "query_name": "dashboardsSheetsAndFields",
        "query_contents": """
            query dashboards_sheets_and_fields {
                dashboardsConnection {
                    nodes {
                        luid
                        name,
                        sheets {
                            name,
                            sheetFieldInstances {
                                name
                            }
                        }
                    }
                }
            }
        """
    },
    { 
        "query_name": "dashboardsAndDataSources",
        "query_contents": """
            query dashboardsAndDataSources {
                dashboardsConnection {
                    nodes {
                        luid
                        name,
                        upstreamDatasources {
                            id,
                            name
                        },
                        workbook {
                            luid,
                            name
                        }
                    }
                }
            }
        """
    }
]