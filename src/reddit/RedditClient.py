import praw 

class RedditClient:
    """Establishes a connection with the reddit api and communicates with the reddit API.
    """
    def __init__(self, client_id, client_secret, user_agent):
        
        self.reddit = praw.Reddit(client_id=client_id, client_secret=client_secret,
                                  user_agent = user_agent)
    
    def fetch_recent_posts(self, subreddit: str, limit: int =200):
        """Yields recent posts and comments from subreddit

        Args:
            subreddit (str): Name of subreddit (without r/)
            limit (int, optional): Max number of posts to be retrieved. does not affect comments. Defaults to 200.

        Yields:
            Dict[str, str, str, float]: A dictionary containing the following keys:
            - "id" (str): The id of the post (abc123)
            - "type" (str): "post" or "comment"
            - "text" (str): the post or comment's text
            - "created" (float): the created_utc time of post in UNIX
        """
        try:
            sub = self.reddit.subreddit(subreddit)
            for post in sub.new(limit=limit):
                yield {"id": post.id, "type":"post", "text": post.title + ' ' + (post.selftext or ''), "created": post.created_utc}
                #get comments
                post.comments.replace_more(limit=0)
                for c in post.comments.list():
                    yield {"id": c.id, "type": "comment", "text": c.body, "created": c.created_utc}
        except:
            print("Error connecting with subreddit. redditclient.py")
    
    