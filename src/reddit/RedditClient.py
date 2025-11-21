import praw 
from models import Post
from datetime import datetime, timezone
from typing import Optional, Tuple, List

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
    def __init__(self, client_id, client_secret, user_agent, connection_pool=None):
        self.reddit = praw.Reddit(client_id=client_id, client_secret=client_secret,
                                  user_agent = user_agent)
        self.connection_pool = connection_pool
        logger.info("Reddit client initialized")
    
    def _get_author_data_from_cache_or_api(self, author, authors_to_cache: List) -> Tuple[str, Optional[float], Optional[int], Optional[int]]:
        """Get author data from cache or Reddit API.
        
        Args:
            author: PRAW author object (can be None for deleted users)
            authors_to_cache: List to collect authors that need to be cached (fetched from API)
            
        Returns:
            Tuple[str, Optional[float], Optional[int], Optional[int]]: 
                (user_id, created_utc, comment_karma, link_karma)
        """
        # Handle deleted users
        if author is None:
            return ("[DELETED]", None, None, None)
        
        username = author.name
        
        # Try to get from cache if connection_pool is provided
        if self.connection_pool:
            cached_data = get_author_data(self.connection_pool, username)
            if cached_data is not None:
                logger.debug(f"Cache hit for author: {username}")
                created_utc, comment_karma, link_karma = cached_data
                return (username, created_utc, comment_karma, link_karma)
        
        # Cache miss or no connection_pool - fetch from Reddit API
        logger.debug(f"Cache miss for author: {username}, fetching from API")
        try:
            created_utc = author.created_utc
            comment_karma = author.comment_karma
            link_karma = author.link_karma
            
            # Collect for batch insert instead of inserting immediately
            if self.connection_pool:
                authors_to_cache.append((username, created_utc, comment_karma, link_karma))
            
            return (username, created_utc, comment_karma, link_karma)
        except Exception as e:
            logger.warning(f"Error fetching author data for {username}: {e}")
            # Return None values if API call fails
            return (username, None, None, None)
    
    def _batch_upsert_authors(self, authors_to_cache: List[Tuple[str, Optional[float], Optional[int], Optional[int]]]) -> None:
        """Batch insert/update author data to cache using connection pool.
        
        Args:
            authors_to_cache: List of tuples (username, created_utc, comment_karma, link_karma)
        """
        if not authors_to_cache or not self.connection_pool:
            return
        
        from psycopg2.extras import execute_batch
        
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        
        try:
            data = []
            for username, created_utc, comment_karma, link_karma in authors_to_cache:
                created_dt = None
                if created_utc is not None:
                    created_dt = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                data.append((username, created_dt, comment_karma, link_karma))
            
            execute_batch(cursor, """
                INSERT INTO authors (username, created_utc, comment_karma, link_karma, last_updated)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (username) 
                DO UPDATE SET 
                    created_utc = EXCLUDED.created_utc,
                    comment_karma = EXCLUDED.comment_karma,
                    link_karma = EXCLUDED.link_karma,
                    last_updated = NOW()
            """, data)
            
            conn.commit()
            logger.debug(f"Batch upserted {len(authors_to_cache)} authors to cache")
        except Exception as e:
            conn.rollback()
            logger.error(f"Error batch upserting authors: {e}")
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
    
    def fetch_recent_posts(self, subreddit: str, limit: int =200):
        """Yields recent posts and comments from subreddit

        Args:
            subreddit (str): Name of subreddit (without r/).
            limit (int, optional): Max number of posts to be retrieved. does not affect comments. Defaults to 200.

        Yields:
            Post: a post dataclass instance representing an entry from the subreddit.
        """
        authors_to_cache = []  # Collect authors fetched from API for batch insert
        
        try:
            logger.debug(f"Fetching {limit} recent posts from r/{subreddit}")

            sub = self.reddit.subreddit(subreddit)
            post_count = 0
            for p in sub.new(limit=limit):
                #get user info for post
                user_id, auth_created_utc, auth_comment_karma, auth_link_karma = \
                    self._get_author_data_from_cache_or_api(p.author, authors_to_cache)
                
                yield Post(
                    p.id, subreddit, "post", p.title + ' ' + (p.selftext or ''), p.created_utc, None, user_id, 
                    p.score, p.num_comments,
                    auth_created_utc, auth_comment_karma, auth_link_karma
                )
                
                post_count += 1
            #comments
            comment_count = 0
            for c in sub.comments(limit=200):
                #get user info for comments
                user_id, auth_created_utc, auth_comment_karma, auth_link_karma = \
                    self._get_author_data_from_cache_or_api(c.author, authors_to_cache)
            
                yield Post(
                    c.id, subreddit, "comment", c.body, c.created_utc, c.submission.id, user_id,
                    c.score, 0,
                    auth_created_utc, auth_comment_karma, auth_link_karma
                )
                comment_count += 1
            
            # Batch insert all authors that were fetched from API
            if authors_to_cache:
                # Remove duplicates (same author might appear in both posts and comments)
                seen = set()
                unique_authors = []
                for author_data in authors_to_cache:
                    username = author_data[0]
                    if username not in seen:
                        seen.add(username)
                        unique_authors.append(author_data)
                
                self._batch_upsert_authors(unique_authors)
            
            logger.debug(f"Fetched {post_count} posts and {comment_count} comments from r/{subreddit}")

        except Exception as e:
            logger.error(f"Error connecting with subreddit '{subreddit}': {e}", exc_info=True)
    
    