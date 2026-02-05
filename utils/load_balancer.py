"""Load balancer for channel selection"""
import random
from typing import Optional
from models.channel import Channel, get_channels_by_model


class LoadBalancer:
    """Load balancer with multiple strategies"""
    
    @staticmethod
    async def select_channel(model: str, strategy: str = "weighted") -> Optional[Channel]:
        """
        Select a channel based on load balancing strategy
        
        Args:
            model: Model name
            strategy: Selection strategy (weighted, priority, round_robin, least_response_time)
        
        Returns:
            Selected channel or None
        """
        channels = await get_channels_by_model(model)
        
        if not channels:
            return None
        
        if len(channels) == 1:
            return channels[0]
        
        if strategy == "weighted":
            return LoadBalancer._weighted_random(channels)
        elif strategy == "priority":
            return LoadBalancer._priority_first(channels)
        elif strategy == "least_response_time":
            return LoadBalancer._least_response_time(channels)
        elif strategy == "round_robin":
            return LoadBalancer._round_robin(channels)
        else:
            return LoadBalancer._weighted_random(channels)
    
    @staticmethod
    def _weighted_random(channels: list[Channel]) -> Channel:
        """
        Weighted random selection based on priority, weight, and success rate
        
        Formula: score = priority * 100 + weight * 10 + success_rate * 5 - (response_time / 1000)
        """
        scores = []
        for channel in channels:
            success_rate = channel.get_success_rate()
            response_penalty = channel.avg_response_time / 1000 if channel.avg_response_time > 0 else 0
            
            # Calculate score
            score = (
                channel.priority * 100 +  # Priority is most important
                channel.weight * 10 +      # Weight is secondary
                success_rate * 5 -         # Success rate bonus
                response_penalty           # Response time penalty
            )
            
            # Ensure minimum score of 1
            score = max(1, score)
            scores.append(score)
        
        # Weighted random selection
        total_score = sum(scores)
        rand = random.uniform(0, total_score)
        
        cumulative = 0
        for i, score in enumerate(scores):
            cumulative += score
            if rand <= cumulative:
                return channels[i]
        
        return channels[-1]
    
    @staticmethod
    def _priority_first(channels: list[Channel]) -> Channel:
        """Select channel with highest priority (already sorted)"""
        return channels[0]
    
    @staticmethod
    def _least_response_time(channels: list[Channel]) -> Channel:
        """Select channel with lowest average response time"""
        # Filter channels with response time data
        channels_with_time = [c for c in channels if c.total_requests > 0]
        
        if not channels_with_time:
            # No response time data, fall back to weighted
            return LoadBalancer._weighted_random(channels)
        
        # Sort by response time (ascending)
        channels_with_time.sort(key=lambda c: c.avg_response_time)
        return channels_with_time[0]
    
    @staticmethod
    def _round_robin(channels: list[Channel]) -> Channel:
        """
        Round robin selection based on total requests
        Select the channel with least total requests
        """
        # Sort by total requests (ascending)
        channels.sort(key=lambda c: c.total_requests)
        return channels[0]


# Global load balancer instance
load_balancer = LoadBalancer()
