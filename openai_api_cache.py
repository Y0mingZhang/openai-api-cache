""" A redis-based cache wrapper for OpenAI API to avoid duplicate requests """
import hashlib
import collections
import pickle
import logging

import redis
import openai

logger = logging.getLogger(name="OpenAIAPICache")

def deterministic_hash(data) -> int:
    try:
        data_str = str(data).encode("utf-8")
    except:
        raise Exception(f"Unable to convert type {type(data)} to string.")
    return int(hashlib.sha512(data_str).hexdigest(), 16)


class FrozenDict:
    """ frozen, hashable mapping """
    def __init__(self, mapping):
        self.data = {}
        for key, value in mapping.items():
            if not isinstance(key, collections.Hashable):
                raise Exception(f"{type(key)} is not hashable")
            if not isinstance(value, collections.Hashable):
                raise Exception(f"{type(value)} is not hashable")
            self.data[key] = value

    def __hash__(self):
        ordered_keys = sorted(self.data.keys(), key=deterministic_hash)
        return deterministic_hash(tuple((k, self.data[k]) for k in ordered_keys))

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        raise Exception("FrozenDict is immutable")

    def __repr__(self):
        return repr(self.data)
    
    def __eq__(self, other):
        return self.data == other.data


class OpenAIAPICache:
    """ A Redis cache wrapper for OpenAI API requests """
    def __init__(self, api_key, port=6379):
        logger.info(f"Setting OpenAI API key: {api_key}")
        openai.api_key = api_key
        logger.info(f"Connecting to Redis DB on port {port}")
        self.r = redis.Redis(host="localhost", port=port)

    def generate(self, **kwargs):
        query = FrozenDict(kwargs)
        hashval = hash(query)
        cache = self.r.hget(hashval, "data")
        if cache is not None:
            query_cached, resp_cached = pickle.loads(cache)
            if query_cached == query:
                logger.debug(f"Matched cache for query")
                return resp_cached
            logger.debug(
                f"Hash matches for query and cache, but contents are not equal. "
                + "Overwriting cache."
            )
        else:
            logger.debug(f"Matching hash not found for query")
        
        logger.debug(f"Request Completion from OpenAI API...")
        resp = openai.Completion.create(**kwargs)
        data = pickle.dumps((query, resp))
        logger.debug(f"Writing query and resp to Redis")
        self.r.hset(hashval, "data", data)
        
        return resp

