import praw 
from models import Post

import logging
logger = logging.getLogger(__name__)

class RedditClient:
    """Establishes a connection with the reddit api and communicates with the reddit API.
    """
    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = praw.Reddit(client_id=client_id, client_secret=client_secret,
                                  user_agent = user_agent)
    
    def fetch_recent_posts(self, subreddit: str, limit: int =200):
        """Yields recent posts and comments from subreddit

        Args:
            subreddit (str): Name of subreddit (without r/).
            limit (int, optional): Max number of posts to be retrieved. does not affect comments. Defaults to 200.

        Yields:
            Post: a post dataclass instance representing an entry from the subreddit.
        """
        try:
            sub = self.reddit.subreddit(subreddit)
            for p in sub.new(limit=limit):
                yield Post(p.id, subreddit, "post", p.title + ' ' + (p.selftext or ''), p.created_utc)
                #get comments
                p.comments.replace_more(limit=0)
                for c in p.comments.list():
                    yield Post(c.id, subreddit, "comment", c.body, c.created_utc)
        except Exception as e:
            logger.error(f"Error connecting with subreddit '{subreddit}': {e}")
    
    