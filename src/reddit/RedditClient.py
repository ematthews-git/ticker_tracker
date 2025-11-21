import praw 
from models import Post
from datetime import datetime, timezone
from typing import Optional, Tuple

import logging
logger = logging.getLogger(__name__)

# Import database functions for author caching
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from storage.Database import get_author_data, upsert_author_data

class RedditClient:
    """Establishes a connection with the reddit api and communicates with the reddit API.
    """
    def __init__(self, client_id, client_secret, user_agent, db_url: Optional[str] = None):
        self.reddit = praw.Reddit(client_id=client_id, client_secret=client_secret,
                                  user_agent = user_agent)
        self.db_url = db_url
        logger.info("Reddit client initialized")
    
    def _get_author_data_from_cache_or_api(self, author) -> Tuple[str, Optional[float], Optional[int], Optional[int]]:
        """Get author data from cache or Reddit API.
        
        Args:
            author: PRAW author object (can be None for deleted users)
            
        Returns:
            Tuple[str, Optional[float], Optional[int], Optional[int]]: 
                (user_id, created_utc, comment_karma, link_karma)
        """
        # Handle deleted users
        if author is None:
            return ("[DELETED]", None, None, None)
        
        username = author.name
        
        # Try to get from cache if db_url is provided
        if self.db_url:
            cached_data = get_author_data(self.db_url, username)
            if cached_data is not None:
                logger.debug(f"Cache hit for author: {username}")
                created_utc, comment_karma, link_karma = cached_data
                return (username, created_utc, comment_karma, link_karma)
        
        # Cache miss or no db_url - fetch from Reddit API
        logger.debug(f"Cache miss for author: {username}, fetching from API")
        try:
            created_utc = author.created_utc
            comment_karma = author.comment_karma
            link_karma = author.link_karma
            
            # Update cache if db_url is provided
            if self.db_url:
                upsert_author_data(self.db_url, username, created_utc, comment_karma, link_karma)
            
            return (username, created_utc, comment_karma, link_karma)
        except Exception as e:
            logger.warning(f"Error fetching author data for {username}: {e}")
            # Return None values if API call fails
            return (username, None, None, None)
    
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
                user_id, auth_created_utc, auth_comment_karma, auth_link_karma = \
                    self._get_author_data_from_cache_or_api(p.author)
                
                yield Post(
                    p.id, subreddit, "post", p.title + ' ' + (p.selftext or ''), p.created_utc, None, user_id, 
                    p.score, p.num_comments,
                    auth_created_utc, auth_comment_karma, auth_link_karma
                )
                
                post_count += 1
            #comments
            comment_count = 0
            for c in sub.comments(limit=200):
                user_id, auth_created_utc, auth_comment_karma, auth_link_karma = \
                    self._get_author_data_from_cache_or_api(c.author)
            
                yield Post(
                    c.id, subreddit, "comment", c.body, c.created_utc, c.submission.id, user_id,
                    c.score, 0,
                    auth_created_utc, auth_comment_karma, auth_link_karma
                )
                comment_count += 1
            
            logger.debug(f"Fetched {post_count} posts and {comment_count} comments from r/{subreddit}")

        except Exception as e:
            logger.error(f"Error connecting with subreddit '{subreddit}': {e}", exc_info=True)
    
    