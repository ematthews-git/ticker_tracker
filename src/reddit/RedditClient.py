import praw 

class RedditClient:
    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = praw.Reddit(client_id=client_id, client_secret=client_secret,
                                  user_agent = user_agent)
    
    def GetRecentPosts(self, subreddit, limit=200):
        sub = self.reddit.subreddit(subreddit)
        for post in sub.new(limit=limit):
            yield post.title + ' ' + (post.selftext or '')
            #get comments
            post.comments.replace_more(limit=0)
            for c in post.comments.list():
                yield c.body