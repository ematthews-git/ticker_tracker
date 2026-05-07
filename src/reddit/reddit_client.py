import praw
from models import Post
import logging

logger = logging.getLogger(__name__)


class RedditClient:
    """Establishes a connection with the reddit api and communicates with the reddit API."""

    def __init__(self, client_id, client_secret, user_agent, connection_pool=None):
        self.reddit = praw.Reddit(
            client_id=client_id, client_secret=client_secret, user_agent=user_agent
        )
        self.connection_pool = connection_pool
        logger.info("Reddit client initialized")

    def _convert_to_post(self, raw_post, subreddit: str) -> Post:
        """Converts a raw Reddit post object to a Post dataclass instance.

        The author username is read directly from the PRAW Submission object —
        it is included in the Reddit listing response and requires no extra API call.
        Posts from deleted/suspended accounts have author=None and are recorded as
        "[DELETED]".

        Args:
            raw_post: PRAW Submission object
            subreddit (str): Name of the subreddit

        Returns:
            Post: A Post dataclass instance representing the Reddit post
        """
        user_id = raw_post.author.name if raw_post.author else "[DELETED]"

        return Post(
            id=raw_post.id,
            subreddit=subreddit,
            type="post",
            text=raw_post.title + " " + (raw_post.selftext or ""),
            link_flair_text=raw_post.link_flair_text,
            created_utc=raw_post.created_utc,
            origin_id=None,
            user_id=user_id,
            score=raw_post.score,
            upvote_ratio=raw_post.upvote_ratio,
            num_comments=raw_post.num_comments,
            author_quality=None,
        )

    def _convert_to_comment(self, raw_comment, subreddit: str) -> Post:
        """Converts a raw Reddit comment object to a Post dataclass instance.

        The author username is read directly from the PRAW Comment object —
        it is included in the Reddit listing response and requires no extra API call.
        Comments from deleted/suspended accounts have author=None and are recorded
        as "[DELETED]".

        Args:
            raw_comment: PRAW Comment object
            subreddit (str): Name of the subreddit

        Returns:
            Post: A Post dataclass instance representing the Reddit comment
        """
        user_id = raw_comment.author.name if raw_comment.author else "[DELETED]"

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
            author_quality=None,
        )

    def fetch_recent_posts(
        self,
        subreddit: str,
        limit: int = 200,
        top_posts_for_comments: int = 20,
        stream_comment_limit: int = 300,
    ) -> tuple[list, list, list]:
        """Fetches recent posts and comments from a subreddit.

        Comments are collected from two sources:
        - Stream: the most recent subreddit-wide comments (up to stream_comment_limit).
        - Per-post: comment trees for the top `top_posts_for_comments` most-discussed new posts.

        Args:
            subreddit (str): Name of subreddit (without r/).
            limit (int): Max number of posts to retrieve. Defaults to 200.
            top_posts_for_comments (int): Number of top posts (by comment count) to fetch
                full comment trees for. Defaults to 20.
            stream_comment_limit (int): Max comments to pull from the subreddit-wide stream.

        Returns:
            tuple[list[Post], list[Post], list[Post]]: (posts, stream_comments, per_post_comments)

        Raises:
            Re-raises any exception from PRAW. Callers are responsible for capturing
            and recording the failure (so the run continues but the failure is visible).
        """
        logger.debug(
            f"Fetching {limit} recent posts and up to {stream_comment_limit} "
            f"stream comments from r/{subreddit}"
        )

        sub = self.reddit.subreddit(subreddit)

        # Fetch raw posts, select top posts for comment trees, then convert
        # and release the PRAW objects as soon as possible.
        raw_posts = list(sub.new(limit=limit))
        posts_to_fetch = sorted(
            [p for p in raw_posts if p.num_comments > 0],
            key=lambda p: p.num_comments,
            reverse=True,
        )[:top_posts_for_comments]
        posts = [self._convert_to_post(p, subreddit) for p in raw_posts]
        del raw_posts

        raw_stream_comments = list(sub.comments(limit=stream_comment_limit))
        stream_comments = [
            self._convert_to_comment(c, subreddit) for c in raw_stream_comments
        ]
        del raw_stream_comments

        raw_per_post_comments = []
        for post in posts_to_fetch:
            post.comments.replace_more(limit=5, threshold=10)
            raw_per_post_comments.extend(post.comments.list())
        del posts_to_fetch
        per_post_comments = [
            self._convert_to_comment(c, subreddit) for c in raw_per_post_comments
        ]
        del raw_per_post_comments

        logger.debug(
            f"Fetched {len(posts)} posts, {len(stream_comments)} stream comments, "
            f"{len(per_post_comments)} per-post comments from r/{subreddit}"
        )
        return posts, stream_comments, per_post_comments

    def fetch_comments_for_posts(
        self, post_ids_and_subreddits: list[tuple[str, str]]
    ) -> list:
        """Fetches current comments for a list of known posts by ID.

        Used by the :30 job to revisit recently active posts and collect comments
        that have appeared since the last :00 run.

        Args:
            post_ids_and_subreddits (list[tuple[str, str]]): List of (post_id, subreddit).

        Returns:
            list[Post]: Comment Post objects ready for process_mentions().
        """
        if not post_ids_and_subreddits:
            return []

        raw_comments_with_sub: list[tuple] = []

        for post_id, subreddit in post_ids_and_subreddits:
            try:
                submission = self.reddit.submission(id=post_id)
                submission.comments.replace_more(limit=5, threshold=10)
                for comment in submission.comments.list():
                    raw_comments_with_sub.append((comment, subreddit))
            except Exception as e:
                logger.warning(f"Failed to fetch comments for post {post_id}: {e}")

        return [
            self._convert_to_comment(comment, subreddit)
            for comment, subreddit in raw_comments_with_sub
        ]
