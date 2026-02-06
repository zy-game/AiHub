"""Load balancer for provider selection"""
import random
from typing import Optional, List


class LoadBalancer:
    """Load balancer with multiple strategies for provider selection"""
    
    def select_provider(self, providers: List, strategy: str = "weighted"):
        """
        Select a provider based on load balancing strategy
        
        Args:
            providers: List of BaseProvider instances
            strategy: Selection strategy (weighted, priority, round_robin, least_response_time)
        
        Returns:
            Selected provider or None
        """
        if not providers:
            return None
        
        if len(providers) == 1:
            return providers[0]
        
        if strategy == "weighted":
            return self._weighted_random(providers)
        elif strategy == "priority":
            return self._priority_first(providers)
        elif strategy == "least_response_time":
            return self._least_response_time(providers)
        elif strategy == "round_robin":
            return self._round_robin(providers)
        else:
            return self._weighted_random(providers)
    
    @staticmethod
    def _weighted_random(providers: List) -> Optional:
        """
        Weighted random selection based on priority, weight, and success rate
        
        Formula: score = priority * 100 + weight * 10 + success_rate * 5 - (response_time / 1000)
        """
        scores = []
        for provider in providers:
            success_rate = provider.get_success_rate()
            response_penalty = provider.avg_response_time / 1000 if provider.avg_response_time > 0 else 0
            
            # Calculate score
            score = (
                provider.priority * 100 +  # Priority is most important
                provider.weight * 10 +      # Weight is secondary
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
                return providers[i]
        
        return providers[-1]
    
    @staticmethod
    def _priority_first(providers: List):
        """Select provider with highest priority (already sorted)"""
        return providers[0]
    
    @staticmethod
    def _least_response_time(providers: List):
        """Select provider with lowest average response time"""
        # Filter providers with response time data
        providers_with_time = [p for p in providers if p.total_requests > 0]
        
        if not providers_with_time:
            # No response time data, fall back to weighted
            return LoadBalancer._weighted_random(providers)
        
        # Sort by response time (ascending)
        providers_with_time.sort(key=lambda p: p.avg_response_time)
        return providers_with_time[0]
    
    @staticmethod
    def _round_robin(providers: List):
        """
        Round robin selection based on total requests
        Select the provider with least total requests
        """
        # Sort by total requests (ascending)
        providers.sort(key=lambda p: p.total_requests)
        return providers[0]


# Global load balancer instance
load_balancer = LoadBalancer()
