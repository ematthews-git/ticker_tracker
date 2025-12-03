import re
import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime, timezone

from models import Post, MentionDataPoint
from storage.database_manager import get_existing_post_ids_batch
from analysis.mention_analyser import MentionAnalyser

import logging
logger = logging.getLogger(__name__)

class TickerMentionScanner:
    """Scans for Ticker Mentions and saves posts to database.
    """
    def __init__(self, valid_tickers, connection_pool=None):
        """
        Args:
            valid_tickers: List of ticker symbols to search for
            connection_pool: The PostgreSQL connection pool (optional)
        """
        self.valid = set(valid_tickers)
        self.connection_pool = connection_pool
        self.mention_analyser = MentionAnalyser()

    def save_post(self, post: Post) -> None:
        """Saves one post to the posts table of database.
        
        Args:
            post (Post): An instance of the Post dataclass.
        """
        if not self.connection_pool:
            raise ValueError("Connection pool is required to save posts")
        
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        try:
            # Convert Unix timestamp to datetime (UTC)
            created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            cursor.execute("""
                INSERT INTO posts (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                """, (post.id, post.subreddit, created_dt, post.text, post.link_flair_text, post.type, post.origin_id, post.user_id, 
                      post.score, post.upvote_ratio, post.num_comments, post.author_quality))
        
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error saving post {post.id}: {e}")
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)

    def _batch_save_posts(self, posts_data: list[tuple]) -> None:
        """Batch saves multiple posts to the database in a single transaction.
        
        Args:
            posts_data: List of tuples (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
        """
        if not posts_data:
            return
        
        if not self.connection_pool:
            raise ValueError("Connection pool is required to save posts")

        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        try:
            execute_batch(cursor, """
                INSERT INTO posts (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
                """, posts_data)
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error batch saving posts: {e}")
            raise
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)
    
    def _find_new_posts(self, post_list: list[Post]) -> list[Post]:
        """Takes a list of posts and finds all posts not already saved in the database.

        Args:
            post_list (list[Post]): Posts to search for new posts within.

        Returns:
            list[Post]: All posts from the passed list which are not yet in the database.
        """
        post_ids_to_check = [p.id for p in post_list]
        existing_ids = set()
        
        if self.connection_pool and post_ids_to_check:
            existing_ids = get_existing_post_ids_batch(self.connection_pool, post_ids_to_check)
            
        logger.info(f"Found {len(existing_ids)} existing posts in batch of {len(post_ids_to_check)}")

        # Collect new posts to batch insert
        new_posts = []

        for post in post_list:
            #skip if already processed
            if post.id in existing_ids:
                continue

            new_posts.append(post)

        return new_posts

    def _posts_to_tuples(self, post_list: list[Post]) -> list[tuple]:
        """Simple convert a list of Post objects to a list of tuples.

        Args:
            post_list (Post): A list of Posts.
                
        Returns:
            list[tuple]: A list of equivalent tuples.
                (post_id, subreddit, created_utc, text, link_flair_text, type, origin_id, user_id, score, upvote_ratio, num_comments, author_quality)
        """
        if not post_list:
            return []
        
        tuples = []
        for post in post_list:
            created_dt = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
            tuples.append((post.id, post.subreddit, created_dt, post.text, post.link_flair_text, post.type, post.origin_id, post.user_id,
                             post.score, post.upvote_ratio, post.num_comments, post.author_quality))
        
        return tuples
    
    def _calculate_weighted_sentiment(self, posts: list[Post], ticker: str) -> float:
        """Calculate weighted average sentiment for a ticker.

        Posts with higher engagement have more weight.

        Args:
            posts (list[Post]): Posts mentioning the ticker.
            ticker (str): The ticker symbol

        Returns:
            float: Weighted sentiment score between -1 and 1
        """
        if not posts: 
            return 0.0
        

        
    #Counts mentions of valid tickers into list of MentionDataPoint objects
    def process_mentions(self, post_list: list[Post]) -> list[MentionDataPoint]:
        """finds the mention of any valid ticker in the list of text parsed and saves each post to db.

        Args:
            post_list (Iterable[Post]): The list of post items to search.

        Returns:
            list[MentionDataPoint]: A list of MentionDataPoint objects representing ticker mentions.
        """
        timestamp = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        
        posts_to_process = self._find_new_posts(post_list)
        new_posts = self._posts_to_tuples(posts_to_process)

        # Batch insert all new posts at once
        if new_posts:
            self._batch_save_posts(new_posts)
            logger.info(f"{len(new_posts)} New posts saved to database")

        # Process ticker mentions for new posts
        # Track detailed metrics per ticker-subreddit combination
        mention_data = {}  # key: (ticker, subreddit) -> {count, users, total_score, total_comments}
        
        for post in posts_to_process:
            #find ticker mentions
            tickers = re.findall(r'\b[A-Z]{2,5}\b', post.text) #captal letters + 2 to 5 characters
            for t in tickers:
                if t in self.valid:
                    key = (t.upper(), post.subreddit)
                    if key not in mention_data:
                        mention_data[key] = {
                            'count': 0,
                            'users': set(),
                            'total_score': 0,
                            'total_comments': 0,
                            'posts': []
                        }
                    mention_data[key]['count'] += 1
                    mention_data[key]['users'].add(post.user_id)
                    mention_data[key]['total_score'] += post.score
                    mention_data[key]['total_comments'] += post.num_comments
                    mention_data[key]['posts'].append(post)
            
        logger.info(f"{len(posts_to_process)} New posts processed")
        
        # Convert mention_data dictionary to list of MentionDataPoint objects
        #avg_sentiment = self.mention_analyser.calculate_weighted_sentiment(data['posts', ticker])
        mention_data_points = []
        for (ticker, subreddit), data in mention_data.items():
            sentiment = self.mention_analyser.analyse_ticker_sentiment(data['posts'], ticker)
            avg_sentiment = sentiment['avg_sentiment']

            mention_data_points.append(
                MentionDataPoint(
                ticker=ticker,
                subreddit=subreddit,
                timestamp=timestamp,
                mention_count=data['count'],
                unique_users=len(data['users']),
                total_score=data['total_score'],
                total_comments=data['total_comments'],
                avg_sentiment=avg_sentiment
                )
            )
        return mention_data_points
    
    def _get_existing_posts_ids(self) -> set:
        """Gets set of all post IDs already in the database

        Returns:
            set: all post IDs
        """
        if not self.connection_pool:
            raise ValueError("Connection pool is required to get existing posts")
        
        conn = self.connection_pool.getconn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT post_id FROM posts")
            existing_ids = {row[0] for row in cursor.fetchall()}
            return existing_ids
        finally:
            cursor.close()
            self.connection_pool.putconn(conn)

   