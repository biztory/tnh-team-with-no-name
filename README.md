# (Tableau) Next Question

This repository contains the code for **(Tableau) Next Question**, a Tableau Next Hackathon entry by Biztory's Team With No Name.

This repository is intended to serve as a reference to some of the code used, and as an example for others trying to achieve similar goals.

```
Copyright (c) 2025 [Biztory]. All rights reserved.

This repository is shared for review/reference only.
Copying, reuse, or distribution of the code or its contents  without explicit permission is prohibited.
```

### Intention

Focusing on the concept of interoperability, our intention is to showcase how Tableau Next and other Salesforce platforms can be connected, and how they can work together to provide people with a seamless experience across products.

We’re mainly looking to combine Tableau Next with Tableau Cloud/Server/Core, as well as Slack. Use of other Salesforce products, features and components (e.g. agentic features) could be considered as well (but is not part of the original project).

### Use Case

More specifically, our use case will be that of a Slack app titled (Tableau) Next Question, which will be the central component that connects Tableau Next and Tableau Core to answer data questions more dynamically and effectively than ever.

The idea is that users can formulate questions in Slack, directed to the app specifically or in any channel, and that we use assets on either Tableau platform to provide an answer. The two demo scenarios described below should illustrate the app’s capabilities.

## Notes on setup

The following few sub-sections contain notes on the setup of different components of this app. This include the Salesforce External Client App (allowing us to interact with Tableau Next and Data Cloud), as well as the Django App (which forms the core of _our_ logic). And also the Slack app.

### Salesforce External Client App Setup

In any (Developer?) Salesforce Org... For Timothy as of 2025-08-06: 1Password "Tableau Next Beta (Datafam)".

Started by setting up a Connected App in the Org, and enable OAuth. This is mostly following these steps: https://developer.salesforce.com/docs/analytics/tableau-next-rest-api/guide/auth_for_sfapi.html

* Ensure your user has as valid email address (not `epic.orgfarm@salesforce.com`) because we will need to receive an auth code by email at some point. If needed, create a new System Administrator account and sign in with that account.
* Go to setup, and create an External Client App.
    * Name, API Name, Contact Email, are obvious.
    * Distribution State: Local
    * ☑️ Enable OAuth
    * (OAuth) Callback URL: `https://timothys-macbook-pro.tail18b7d.ts.net/oauth2/callback` (though not used in this case?)
    * (OAuth) scopes: `Manage user data via APIs (api)`, `Perform requests at any time (refresh_token, offline_access)`, `Access the Salesforce API Platform (sfap_api)`.
    * ☑️ Enable Client Credentials Flow
    * ☑️ Issue JWT Web Token (JWT)-based access tokens for named users
* On the next page (to manage/configure the External Client App), Edit Policies (i.e. click edit on the Policies tab):
    * ☑️ Enable Client Credentials Flow
    * Specify the Run As Username (in this case, timothy.vermeiren+hackathon@biztory.be)
    * Specify "Named User JWT-Based Access Token Settings": e.g. 30 minutes
* Obtain the Consumer Key and Secret
    * Back on the Client Application's details page.
    * Settings tab
    * OAuth Settings section
    * Click the button under App Settings, "Consumer Key and Secret"
    * Store these securely + as environment variables for the app
* Also capture our Salesforce domain:
    * "My Domain" through quick find in Org settings
    * Capture "Current My Domain URL", also in env vars.
    * E.g.: `https://orgfarm-3add3657bc.my.salesforce.com`

### Development Environment + Django App Setup

* (Generic) development environment setup _from this repository_:
    * Clone this repository into a folder.
    * Ensure you have python3.11 or later installed.
    * Create a virtual environment in the folder.  
    ```python3.11 -m venv .venv```
    * Activate it (macOS, Linux):  
    ```source .venv/bin/activate```
    * Install dependencies:  
    ```python -m pip install -r requirements.txt```
    * Configure environment variables (see below) in `.env`.
    * Perform Django migrations:
    ```python manage.py migrate```
    * Create a Django superuser.
    * Ready to continue developing, or to demo!
* (Generic) development environment setup _from scratch_:
    * Ensure you have python3.11 or later installed.
    * Create a virtual environment in the folder:  
    ```python3.11 -m venv .venv```
    * Activate it (macOS, Linux):  
    ```source .venv/bin/activate```
    * Install Django etc.:  
    ```python -m pip install Django django-encrypted-model-fields django-q2 python-dotenv requests slack_sdk```
    * Create Django project in this directory:  
    ```django-admin startproject tableau_next_question .```
    * Create Django app in this directory:  
    ```django-admin startapp core```
    * The usual Django housekeeping:  
        * ```python manage.py makemigrations``` (~~we don't need models in the basic version of this app~~ we need a model to store Slack credentials, at least.)
        * ```python manage.py migrate```
        * "[Write your first view](https://docs.djangoproject.com/en/5.2/intro/tutorial01/#write-your-first-view)" stuff: set up `urls.py` in core, refer to that file, etc.
        * Review `settings.py`, add `.env`.
        * Create a Django superuser.

### Slack App Setup

Probably easiest as a Slack workspace/organization owner. Note that this will be set up as:

* One specific Slack app per developer, for specific use with their development environment.
* One production Slack app for our hosted version (if/when applicable).

Steps to set this up:
* Ensure the Slack [endpoints for responding to challenges](https://api.slack.com/events-api#event_subscriptions) are set up.
* Ensure you have a host name Slack can reach (ask for help on this one, it's difficult). In summary, we need to expose your local Django instance to the internet.
* Create Slack app (https://api.slack.com/apps/)
    * From scratch.
    * App name:
        * If dev: `DEV Timothy Tableau Next Question`
        * If prd: `Tableau Next Question`
    * Workspace: wherever you can.
    * Capture Client ID and Secret in `.env`. And verification token.
    * OAuth & Permissions:
        * Add Bot Token Scopes: see Timothy's DEV app for list of scopes.
        * Install app to workspace
    * Copy the Bot User OAuth Token from this same page after installing the app.
    * Using the Django built-in admin, capture the Slack app's bot credentials.
        * Core ➡️ Slack credentials ➡️ add
        * Slack app: app ID from the URL of the page where you're configuring the app.
        * Slack workspace ID: get this from your workspace (`T041ZT57U` for Biztory).
        * Slack workspace bot user id: leave blank for now.
        * Slack workspace bot user access token: the OAuth token from above.
    * Open Slack and find this bot. Update the data above once more with the bot user id (member id when found in Slack).
* Slack app: Event Subscriptions
    * In the app configuration area, head to Event subscriptions.
    * Enable events and specify the `/slack/event` request URL for your Django app, reachable from outside. I.e. expose your local Django instance to the internet (above).  
    E.g. if using tailscale, based on your hostname: `https://timothys-macbook-pro.tail18b7d.ts.net/slack/event`
    * As soon as you paste the URL, if set up correctly, it will be verified.
    * Subscribe to bot events: `app_mention` and `message.im`.
    * Save changes, reinstall app to workspace (no need to repeat any of the steps above after reinstalling).
* Slack app: Interactivity & Shortcuts
    * Same as the above, but with `/slack/interaction` instead of `event`.
    * Save changes.
* Slack app: app home:
    * Tick "Always show my bot as online"
    * Tick "Allow users to send Slash commands and messages from the chat tab"

### OpenAI API setup

Have an app set up on the OpenAI API platform and put its credentials in the Built-in Admin page ➡️ Core ➡️ OpenAI Settings.