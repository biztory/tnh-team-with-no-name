import re, unicodedata

def slugify(value, allow_unicode=False):
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")

def remove_fields_from_dictionary(target_dict:dict, fields_to_remove:list) -> dict:
    """
    Remove specified fields from a dictionary. This function traverses the whole dictionary, and goes into lists and nested dictionaries where needed, removing any field which has a name/key specified in fields_to_remove.

    Returns the modified dictionary, but keep in mind that it modifies the dictionary in place too.
    """
    for field in fields_to_remove:
        target_dict.pop(field, None)
    for key, value in target_dict.items():
        if isinstance(value, dict):
            remove_fields_from_dictionary(value, fields_to_remove)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    remove_fields_from_dictionary(item, fields_to_remove)

    return target_dict

# "Slack markdown", which we needed originally to convert OpenAI API output for Slack, but could be useful elsewhere.
def convert_to_slack_markdown(original_content):
    """
    Converts general Markdown to Slack-compatible Markdown.
    """
    # Replace headers (e.g., # Header) with bold text
    content = re.sub(r'(?m)^#+\s*(.+)', r'*\1*', original_content)

    # Replace bold (**text** or __text__) with Slack-style bold (*text*)
    content = re.sub(r'\*\*(.*?)\*\*', r'*\1*', content)
    content = re.sub(r'__(.*?)__', r'*\1*', content)

    # Replace italic (*text* or _text_) with Slack-style italic (_text_)
    content = re.sub(r'\*(.*?)\*', r'_\1_', content)
    content = re.sub(r'_(.*?)_', r'_\1_', content)

    # Remove strikethrough (~~text~~) since Slack doesn't support it
    content = re.sub(r'~~(.*?)~~', r'\1', content)

    # Replace inline code (`code`) with Slack-style backticks (`code`)
    content = re.sub(r'`([^`]+)`', r'`\1`', content)

    # Replace code blocks (```code```) with Slack-style triple backticks
    content = re.sub(r'```(.*?)```', r'```\1```', content, flags=re.DOTALL)

    # Strip unsupported Markdown (e.g., links [text](url), images ![alt](url))
    content = re.sub(r'!$begin:math:display$.*?$end:math:display$$begin:math:text$.*?$end:math:text$', '', content)  # Remove images
    content = re.sub(r'$begin:math:display$(.*?)$end:math:display$$begin:math:text$.*?$end:math:text$', r'\1', content)  # Keep link text only

    # Return the cleaned, Slack-compatible markdown
    return content.strip()
