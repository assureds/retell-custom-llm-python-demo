import os
import json
import redis
from typing import Dict, Optional

class RedisMetadataStore:
    """Stores and retrieves provider metadata from Redis"""
    
    def __init__(self):
        redis_url = os.environ.get("REDIS_URL")
        redis_enabled = os.environ.get("REDIS_ENABLED", "false").lower() == "true"
        
        print(f"\n{'='*70}")
        print(f"🔴 REDIS INITIALIZATION")
        print(f"{'='*70}")
        print(f"REDIS_ENABLED: {redis_enabled}")
        print(f"REDIS_URL exists: {bool(redis_url)}")
        
        self.enabled = redis_enabled and bool(redis_url)
        
        if self.enabled:
            try:
                self.client = redis.from_url(redis_url, decode_responses=True)
                self.client.ping()
                print(f"✅ Redis connection successful")
                print(f"{'='*70}\n")
            except Exception as e:
                print(f"❌ Redis connection failed: {str(e)}")
                print(f"Falling back to memory storage")
                print(f"{'='*70}\n")
                self.enabled = False
                self.memory_store = {}
        else:
            print(f"⚠️  Redis disabled or not configured")
            print(f"{'='*70}\n")
            self.memory_store = {}
    
    def store_metadata(self, phone_number: str, metadata: Dict) -> bool:
        """Store provider metadata in Redis"""
        try:
            normalized_phone = ''.join(c for c in phone_number if c.isdigit() or c == '+')
            key = f"provider_metadata:{normalized_phone}"
            value = json.dumps(metadata)
            
            if self.enabled and hasattr(self, 'client'):
                self.client.setex(key, 3600, value)
                print(f"✅ Redis STORE: {key} (TTL: 3600s)")
            else:
                self.memory_store[key] = metadata
                print(f"✅ MEMORY STORE: {key}")
            
            return True
        except Exception as e:
            print(f"❌ Error storing metadata: {str(e)}")
            return False
    
    def retrieve_metadata(self, phone_number: str) -> Optional[Dict]:
        """Retrieve provider metadata from Redis"""
        try:
            normalized_phone = ''.join(c for c in phone_number if c.isdigit() or c == '+')
            key = f"provider_metadata:{normalized_phone}"
            
            if self.enabled and hasattr(self, 'client'):
                value = self.client.get(key)
                if value:
                    metadata = json.loads(value)
                    print(f"✅ Redis RETRIEVE: {key} - found {len(metadata)} fields")
                    return metadata
                else:
                    print(f"⚠️  Redis RETRIEVE: {key} - not found")
                    return None
            else:
                if key in self.memory_store:
                    metadata = self.memory_store[key]
                    print(f"✅ MEMORY RETRIEVE: {key} - found {len(metadata)} fields")
                    return metadata
                else:
                    print(f"⚠️  MEMORY RETRIEVE: {key} - not found")
                    return None
        except Exception as e:
            print(f"❌ Error retrieving metadata: {str(e)}")
            return None
    
    def delete_metadata(self, phone_number: str) -> bool:
        """Delete provider metadata"""
        try:
            normalized_phone = ''.join(c for c in phone_number if c.isdigit() or c == '+')
            key = f"provider_metadata:{normalized_phone}"
            
            if self.enabled and hasattr(self, 'client'):
                self.client.delete(key)
                print(f"✅ Redis DELETE: {key}")
            else:
                if key in self.memory_store:
                    del self.memory_store[key]
                    print(f"✅ MEMORY DELETE: {key}")
            
            return True
        except Exception as e:
            print(f"❌ Error deleting metadata: {str(e)}")
            return False


redis_store = RedisMetadataStore()
