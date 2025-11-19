import praw 
from models import Post
from datetime import datetime, timezone

import logging
logger = logging.getLogger(__name__)

class RedditClient:
    """Establishes a connection with the reddit api and communicates with the reddit API.
    """
    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = praw.Reddit(client_id=client_id, client_secret=client_secret,
                                  user_agent = user_agent)
        logger.info("Reddit client initialized")
    
    def fetch_recent_posts(self, subreddit: str, limit: int =200):
        """Yields recent posts and comments from subreddit

        Args:
            subreddit (str): Name of subreddit (without r/).
            limit (int, optional): Max number of posts to be retrieved. does not affect comments. Defaults to 200.

        Yields:
            Post: a post dataclass instance representing an entry from the subreddit.
        """
        try:
            now_utc = datetime.now(timezone.utc)
            logger.debug(f"Fetching {limit} recent posts from r/{subreddit}")

            sub = self.reddit.subreddit(subreddit)
            post_count = 0
            for p in sub.new(limit=limit):
                yield Post(p.id, subreddit, "post", p.title + ' ' + (p.selftext or ''), p.created_utc, None)
                post_count += 1
                #get comments
                # p.comments.replace_more(limit=0)
                # for c in p.comments.list():
                #     yield Post(c.id, subreddit, "comment", c.body, c.created_utc)
            #comments
            comment_count = 0
            for c in sub.comments(limit=200):
                yield Post(c.id, subreddit, "comment", c.body, c.created_utc, c.submission.id)
                comment_count += 1
            
            logger.debug(f"Fetched {post_count} posts and {comment_count} comments from r/{subreddit}")

        except Exception as e:
            logger.error(f"Error connecting with subreddit '{subreddit}': {e}", exc_info=True)
    
    