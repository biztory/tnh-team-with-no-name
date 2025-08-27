import markdown, html2text
from slackify_markdown import slackify_markdown

class FormattedMessage:
    """
    Write a formatted message in Markdown and convert it to different formats.
    This class provides methods to convert the message to Slack format, HTML for email, plain text for email, and a custom markup format (future).
    """
    def __init__(self, markdown_text):
        self.markdown = markdown_text

    def for_slack(self):
        return slackify_markdown(self.markdown)

    def for_email_html(self):
        return markdown.markdown(self.markdown)

    def for_email_text(self):
        html = self.for_email_html()
        return html2text.html2text(html)

    def for_custom_markup(self):
        # custom conversion logic here
        return self.markdown