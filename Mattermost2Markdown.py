"""
project:    Mattermost2Markdown
author:     Simon Eller
license:    MIT
repo:       https://github.com/simon-eller/Mattermost2Markdown
"""

import requests, json, os, time, datetime

from zoneinfo import ZoneInfo

# INSERT YOUR DATA HERE
MATTERMOST_SERVER   = "<server hostname>"
SESSION_TOKEN       = "<your personal session token>"
TEAM                = "<your team>"
USER_NAME           = "<your user name>"

DEFAULT_TIMEOUT = 15

# array of known users to translate usernames into real names
known_users = {}

zone_info = ZoneInfo("Europe/Rome")

def mattermost_channel_content_to_markdown(channel_id, output_folder):
    """
    This function exports every message including attachments of a given Mattermost channel.

    Args:
        channel_id: the id of the channel you want to export
        output_folder: the path to store the final Markdown file and attachments
    """

    # create the chat.md Markdown file in the given folder
    output_file = output_folder + "/chat.md"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # open the Markdown file to write into it
    with open(output_file, 'w', encoding='utf-8') as f:
        page = 0        # variable to store current page
        per_page = 50   # here ou could change the page size (count of messages in one API call)
        channel_posts = {}
        channel_posts_ids = []

        while True:
            # get messages from API
            posts = get_json_request(f"channels/{channel_id}/posts?page={page}&per_page={per_page}")

            # break if there are no more messages in API response
            if not posts["order"]:
                break

            for post in posts["posts"]:
                channel_posts.update(posts['posts'])

            for post_id in posts["order"]:
                channel_posts_ids.append(post_id)

            page += 1               # next page
            time.sleep(1)           # a little break to not overcharge the server

        channel_posts_ids.reverse()

        # a new entry for every message in the Markdown file; the correct order of posts is stored in a list
        for post_id in channel_posts_ids:
            # encapsulate the array for the current message
            post = channel_posts[post_id]

            # convert UNIX timestamp into datetime format
            local_time = datetime.datetime.fromtimestamp(int(post['create_at'])/1000,
                                                         zone_info)

            # if id of the user of current message is not assigned already to a real name
            if post['user_id'] not in known_users:
                # get user information
                user = get_json_request(f"users/{post['user_id']}")
                known_users[post['user_id']] = get_user_display_name(user)

            # write message to Markdown
            f.write(f"**{known_users[post['user_id']]}** ({local_time}):\n")
            f.write(post['message'] + '\n')

            # download attachments
            if 'files' in post["metadata"]:
                for file_info in post['metadata']["files"]:
                    file_id = file_info['id']
                    file_url = f"files/{file_id}"
                    file_extension = file_info['extension']
                    file_name = file_id + "." + file_extension
                    file_path = output_folder + "/" + file_name

                    image_extensions = ["jpg","jpeg","png","gif","heic","heif","tiff","webp"]

                    try:
                        # download attachment and save it to given folder
                        response = get_request(file_url, stream=True)
                        with open(file_path, 'wb') as out_file:
                            for chunk in response.iter_content(1024):
                                out_file.write(chunk)

                        # if the file is an image then embed it into the Markdown file with correct syntax
                        if file_extension in image_extensions:
                            f.write(f"![{file_name}]({file_name})\n")

                        # if file is not an image then link it into the Markdown file
                        else:
                            f.write(f"[{file_name}]({file_name})")

                    except requests.exceptions.RequestException as e:
                        print(f"Error while downloading {file_url}: {e}")

            f.write("\n\n")     # line break


def get_request(api_req, **kwargs):
    headers = {
        "Authorization": "Bearer " + SESSION_TOKEN
    }

    return requests.get(f"https://{MATTERMOST_SERVER}/api/v4/{api_req}",
                        headers=headers, timeout=DEFAULT_TIMEOUT, *kwargs)

def get_json_request(api_req):
    return json.loads(get_request(api_req).text)

def get_user_display_name(user):
    name = f"{user['first_name']} {user['last_name']}".strip()
    return f"{name} ({user['username']})"


if __name__ == "__main__":
    me = get_json_request(f"users/username/{USER_NAME}")

    my_timezone = me["timezone"]
    if my_timezone["useAutomaticTimezone"] and my_timezone["automaticTimezone"]:
        zone_info = ZoneInfo(my_timezone["automaticTimezone"])
    elif my_timezone["manualTimezone"]:
        zone_info = ZoneInfo(my_timezone["manualTimezone"])

    teams = get_json_request("teams")
    [team] = [team for team in teams if team['name'] == TEAM]

    my_channels = get_json_request(f"users/{me['id']}/teams/{team['id']}/channels")
    for channel in my_channels:
        name = channel['name']

        if not channel['total_msg_count']:
            continue

        if channel['type'] == 'D':
            user_id = channel['name'].split('__')[-1]
            user = get_json_request(f"/users/{user_id}")
            name = get_user_display_name(user)
            known_users[user_id] = name
        elif channel['display_name']:
            name = channel['display_name']

        if not name.strip():
            print(f"Skipping ({channel['id']}) ({channel['total_msg_count']})")
            continue

        print(f"Processing {name} ({channel['id']}) ({channel['total_msg_count']})")
        mattermost_channel_content_to_markdown(channel['id'], name)
