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
            logger.debug(f"Fetching {limit} recent posts from r/{subreddit}")

            sub = self.reddit.subreddit(subreddit)
            post_count = 0
            for p in sub.new(limit=limit):
                if p.author:
                    user_id = p.author.name
                    auth_created_utc = p.author.created_utc
                    auth_comment_karma = p.author.comment_karma
                    auth_link_karma = p.author.link_karma
                else:
                    user_id = "[DELETED]"
                    auth_created_utc = None
                    auth_comment_karma = None
                    auth_link_karma = None
                
                yield Post(
                    p.id, subreddit, "post", p.title + ' ' + (p.selftext or ''), p.created_utc, None, user_id, 
                    p.score, p.num_comments,
                    auth_created_utc, auth_comment_karma, auth_link_karma
                )
                
                post_count += 1
            #comments
            comment_count = 0
            for c in sub.comments(limit=200):
                if c.author:
                    user_id = c.author.name
                    auth_created_utc = c.author.created_utc
                    auth_comment_karma = c.authour.comment_karma
                    auth_link_karma = c.author.link_karma
                else:
                    user_id = "[DELETED]"
                    auth_created_utc = None
                    auth_comment_karma = None
                    auth_link_karma = None
            
                yield Post(
                    c.id, subreddit, "comment", c.body, c.created_utc, c.submission.id, user_id,
                    c.score, 0,
                    auth_created_utc, auth_comment_karma, auth_link_karma
                )
                comment_count += 1
            
            logger.debug(f"Fetched {post_count} posts and {comment_count} comments from r/{subreddit}")

        except Exception as e:
            logger.error(f"Error connecting with subreddit '{subreddit}': {e}", exc_info=True)
    
    