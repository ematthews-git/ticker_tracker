import praw 
from models import Post, Author
from datetime import datetime, timezone
from typing import Optional, List

import logging
logger = logging.getLogger(__name__)

# Import database functions for author caching
from storage.database_manager import get_author_data, upsert_author_data
from utils.helper import convert_unix_to_datetime_utc
from praw.models import Redditor, Submission, Comment

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
                created_utc=None,
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
            #This either adds or updates each author passed
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
    
    def _process_missing_authors(self, missing_author_objects: dict[str, Redditor], cached_authors: dict[str, Author]) -> None:
        """Fetches missing authors from API. Updates cached_authors with missing authors retrieved.

        Args:
            missing_author_objects (dict[str, Redditor]): A dict mapping the authors name to the Redditor object as returned by PRAW.
            cached_authors (dict[str, Author]): A dict mapping the authors name to the local Author object.
        
        Returns:
            list[Author]: A list of authors which need to be added to the cache.
        """

        authors_to_cache = []

        for username, author_praw in missing_author_objects.items():
            try:
                # Fetch attributes to force API call if needed (though usually lazy loaded)
                # For PRAW, accessing attributes triggers the fetch
                created_utc_float = author_praw.created_utc
                comment_karma = author_praw.comment_karma
                link_karma = author_praw.link_karma
                
                created_utc_dt = convert_unix_to_datetime_utc(created_utc_float)
                
                author_obj = Author(
                    username=username,
                    created_utc=created_utc_dt,
                    comment_karma=comment_karma if comment_karma is not None else 0,
                    link_karma=link_karma if link_karma is not None else 0,
                    last_updated=datetime.now(timezone.utc)
                )
                cached_authors[username] = author_obj
                authors_to_cache.append(author_obj)
            except Exception as e:
                logger.warning(f"Error fetching author data for {username}: {e}")
                # Use default for failed fetches
                cached_authors[username] = Author.deleted() # Or default
                if username not in cached_authors: # If Author.deleted() didn't set it (it returns an object)
                        cached_authors[username] = Author(
                        username=username,
                        created_utc=None,
                        comment_karma=0,
                        link_karma=0,
                        last_updated=datetime.now(timezone.utc)
                    )
    
    def _extract_unique_author_names(self, *item_list) -> set:
        """Gets all unique authors from any number of lists of posts/comments

        Args:
            *item_list: Variable number of lists containg PRAW Submission or Comments.

        Returns:
            set: Set of unique author names (str).
        """
        if not item_list:
            return set()
        
        author_names = set()
        
        for list in item_list:
            for p in list:
                if p.author:
                    author_names.add(p.author.name)

        return author_names
    
    def _resolve_authors(self, raw_posts: list[Submission], raw_comments: list[Comment]) -> dict[str, Author]:
        """Handles author resolution pipeline.

        Finds all cached authors for given posts, 

        Args:
            raw_posts (list[Submission]): List of PRAW submission objects.
            raw_comments (list[Comment]): List of PRAW comment objects.

        Returns:
            dict[str, Author]: All authors from post/comments which are in the cache.
        """
        #Gets all author names from the post/comments
        author_names = self._extract_unique_author_names(raw_posts, raw_comments)

        #Get all authors which are in the cache
        cached_authors = {}
        if self.connection_pool and author_names:
            from storage.database_manager import get_authors_batch
            cached_authors = get_authors_batch(self.connection_pool, list(author_names))
            logger.debug(f"Batch cache hit for {len(cached_authors)}/{len(author_names)} authors")
        
        #Identify authors not in cache (or outdated)
        missing_authors = []
        for name in author_names:
            if name not in cached_authors:
                missing_authors.append(name)
        
        # Map username -> PRAW Redditor object for missing ones
        missing_author_objects = {}
        if missing_authors:
            logger.debug(f"Fetching {len(missing_authors)} missing authors from API")
            # Scan posts/comments to find the PRAW objects
            for item in raw_posts + raw_comments:
                if item.author and item.author.name in missing_authors and item.author.name not in missing_author_objects:
                    missing_author_objects[item.author.name] = item.author
            
        #Gets list of missing authors, also cached_authors is updated to include the processed missing ones
        authors_to_cache = self._process_missing_authors(missing_author_objects, cached_authors)

        #Batch upsert new authors
        if authors_to_cache:
            self._batch_upsert_authors(authors_to_cache)
        
        return cached_authors

    def _convert_to_post(self, raw_post, subreddit: str, cached_authors: dict) -> Post:
        """Converts a raw Reddit post object to a Post dataclass instance.
        
        Args:
            raw_post: PRAW Submission object
            subreddit (str): Name of the subreddit
            cached_authors (dict): Dictionary mapping author names to Author objects
            
        Returns:
            Post: A Post dataclass instance representing the Reddit post
        """
        author_name = raw_post.author.name if raw_post.author else None
        
        # Use cached author object or mark as deleted
        if author_name and author_name in cached_authors:
            author_obj = cached_authors[author_name]
            user_id = author_obj.username
        else:
            user_id = "[DELETED]"
        
        return Post(
            id=raw_post.id,
            subreddit=subreddit,
            type="post",
            text=raw_post.title + ' ' + (raw_post.selftext or ''),
            link_flair_text=raw_post.link_flair_text,
            created_utc=raw_post.created_utc,
            origin_id=None,
            user_id=user_id,
            score=raw_post.score,
            upvote_ratio=raw_post.upvote_ratio,
            num_comments=raw_post.num_comments,
            author_quality=None
        )

    def _convert_to_comment(self, raw_comment, subreddit: str, cached_authors: dict) -> Post:
        """Converts a raw Reddit comment object to a Post dataclass instance.
        
        Args:
            raw_comment: PRAW Comment object
            subreddit (str): Name of the subreddit
            cached_authors (dict): Dictionary mapping author names to Author objects
            
        Returns:
            Post: A Post dataclass instance representing the Reddit comment
        """
        author_name = raw_comment.author.name if raw_comment.author else None
        
        # Use cached author object or mark as deleted
        if author_name and author_name in cached_authors:
            author_obj = cached_authors[author_name]
            user_id = author_obj.username
        else:
            user_id = "[DELETED]"
        
        return Post(
            id=raw_comment.id,
            subreddit=subreddit,
            type="comment",
            text=raw_comment.body,
            link_flair_text=None,
            created_utc=raw_comment.created_utc,
            origin_id=raw_comment.submission.id,
            user_id=user_id,
            score=raw_comment.score,
            upvote_ratio=None,
            num_comments=0,
            author_quality=None
        )

    def fetch_recent_posts(self, subreddit: str, limit: int = 200):
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
            
            #Fetch all raw posts and comments first
            raw_posts = list(sub.new(limit=limit))
            raw_comments = list(sub.comments(limit=200))
            
            cached_authors = self._resolve_authors(raw_posts, raw_comments)
                
            #Yield Posts
            post_count = 0
            for p in raw_posts:
                post_obj = self._convert_to_post(p, subreddit, cached_authors)
                yield post_obj
                post_count += 1
            #Yield Comments
            comment_count = 0
            for c in raw_comments:
                post_obj = self._convert_to_comment(c, subreddit, cached_authors)
                yield post_obj
                comment_count += 1

            logger.debug(f"Fetched {post_count} posts and {comment_count} comments from r/{subreddit}")

        except Exception as e:
            logger.error(f"Error connecting with subreddit '{subreddit}': {e}", exc_info=True)