import logging
try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    HAS_TEXTBLOB = False

logger = logging.getLogger(__name__)

def analyze_sentiment(text):
    """
    Returns a sentiment score between 0.0 (negative) and 1.0 (positive).
    Default is 0.5 (neutral).
    """
    if not text:
        return 0.5
        
    if HAS_TEXTBLOB:
        try:
            # TextBlob polarity is -1.0 to 1.0. We map it to 0.0 to 1.0
            polarity = TextBlob(text).sentiment.polarity
            # Map -1 -> 0, 0 -> 0.5, 1 -> 1
            return (polarity + 1) / 2
        except Exception as e:
            logger.warning(f"TextBlob sentiment analysis failed: {e}")
    
    # Fallback: Basic keyword scoring
    text_lower = text.lower()
    positive_words = ['good', 'great', 'awesome', 'excellent', 'amazing', 'love', 'best', 'fantastic', 'happy', 'thanks', 'thank']
    negative_words = ['bad', 'terrible', 'awful', 'horrible', 'hate', 'worst', 'disappointed', 'sad', 'poor']
    
    score = 0.5
    for word in positive_words:
        if word in text_lower:
            score += 0.1
    
    for word in negative_words:
        if word in text_lower:
            score -= 0.1
            
    return max(0.0, min(1.0, score))
