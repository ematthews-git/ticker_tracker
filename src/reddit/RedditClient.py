import praw 
from models import Post, Author
from datetime import datetime, timezone
from typing import Optional, List

import logging
logger = logging.getLogger(__name__)

# Import database functions for author caching
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from storage.Database import get_author_data, upsert_author_data
from utils.helper import convert_unix_to_datetime_utc

class RedditClient:
    """Establishes a connection with the reddit api and communicates with the reddit API.
    """
    def __init__(self, client_id, client_secret, user_agent, connection_pool=None):
        self.reddit = praw.Reddit(client_id=client_id, client_secret=client_secret,
                                  user_agent = user_agent)
        self.connection_pool = connection_pool
        logger.info("Reddit client initialized")
    
    def _get_author_data_from_cache_or_api(self, author, authors_to_cache: List[Author]) -> Author:
        """Get author data from cache or Reddit API.
        
        Args:
            author: PRAW author object (can be None for deleted users)
            authors_to_cache: List to collect Author objects that need to be cached (fetched from API)
            
        Returns:
            Author: Author object (with username="[DELETED]" for deleted users)
        """
        # Handle deleted users
        if author is None:
            return Author.deleted()
        
        username = author.name
        
        # Try to get from cache if connection_pool is provided
        if self.connection_pool:
            cached_author = get_author_data(self.connection_pool, username)
            if cached_author is not None:
                logger.debug(f"Cache hit for author: {username}")
                return cached_author
        
        # Cache miss or no connection_pool - fetch from Reddit API
        logger.debug(f"Cache miss for author: {username}, fetching from API")
        try:
            created_utc_float = author.created_utc
            comment_karma = author.comment_karma
            link_karma = author.link_karma
            
            # Convert Unix timestamp to datetime
            created_utc_dt = convert_unix_to_datetime_utc(created_utc_float)
            
            # Create Author object
            author_obj = Author(
                username=username,
                created_utc=created_utc_dt,
                comment_karma=comment_karma if comment_karma is not None else 0,
                link_karma=link_karma if link_karma is not None else 0,
                last_updated=datetime.now(timezone.utc)
            )
            
            # Collect for batch insert instead of inserting immediately
            if self.connection_pool:
                authors_to_cache.append(author_obj)
            
            return author_obj
        except Exception as e:
            logger.warning(f"Error fetching author data for {username}: {e}")
            # Return Author object with default values if API call fails
            return Author(
                username=username,
                created_utc=datetime.fromtimestamp(0, tz=timezone.utc),
                comment_karma=0,
                link_karma=0,
                last_updated=datetime.now(timezone.utc)
            )
    
    def _batch_upsert_authors(self, authors_to_cache: List[Author]) -> None:
        """Batch insert/update author data to cache using connection pool.
        
        Args:
            authors_to_cache: List of Author objects to cache
        """
        if not authors_to_cache or not self.connection_pool:
            return
        
        from psycopg2.extras import execute_batch
        
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()
        
        try:
            data = []
            for author in authors_to_cache:
                data.append((author.username, author.created_utc, author.comment_karma, author.link_karma))
            
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
        authors_to_cache = []  # Collect Author objects fetched from API for batch insert
        
        try:
            logger.debug(f"Fetching {limit} recent posts from r/{subreddit}")

            sub = self.reddit.subreddit(subreddit)
            post_count = 0
            for p in sub.new(limit=limit):
                #get user info for post
                author_obj = self._get_author_data_from_cache_or_api(p.author, authors_to_cache)
                
                yield Post(
                    id=p.id, 
                    subreddit=subreddit, 
                    type="post", 
                    text=p.title + ' ' + (p.selftext or ''), 
                    created_utc=p.created_utc, 
                    origin_id=None, 
                    user_id=author_obj.username, 
                    score=p.score, 
                    num_comments=p.num_comments,
                    author_quality=None
                )
                
                post_count += 1
            #comments
            comment_count = 0
            for c in sub.comments(limit=200):
                #get user info for comments
                author_obj = self._get_author_data_from_cache_or_api(c.author, authors_to_cache)
            
                yield Post(
                    id=c.id, 
                    subreddit=subreddit, 
                    type="comment", 
                    text=c.body, 
                    created_utc=c.created_utc, 
                    origin_id=c.submission.id, 
                    user_id=author_obj.username,
                    score=c.score, 
                    num_comments=0,
                    author_quality=None
                )
                comment_count += 1
            
            # Batch insert all authors that were fetched from API
            if authors_to_cache:
                # Remove duplicates (same author might appear in both posts and comments)
                seen = set()
                unique_authors = []
                for author in authors_to_cache:
                    if author.username not in seen:
                        seen.add(author.username)
                        unique_authors.append(author)
                
                self._batch_upsert_authors(unique_authors)
            
            logger.debug(f"Fetched {post_count} posts and {comment_count} comments from r/{subreddit}")

        except Exception as e:
            logger.error(f"Error connecting with subreddit '{subreddit}': {e}", exc_info=True)
    
    