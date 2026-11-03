-- Redis TIME avoids clock skew across gateway replicas.
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local cooldown = redis.call('PTTL', KEYS[4])
if cooldown > 0 then return {4, cooldown} end
for i = 1, 2 do
    redis.call('ZREMRANGEBYSCORE', KEYS[i], '-inf', now - 60000)
end
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now)
-- Check all constraints BEFORE charging any. Rejected calls never consume RPM.
for i = 1, 2 do
    if redis.call('ZCARD', KEYS[i]) >= tonumber(ARGV[i]) then
        local oldest = redis.call('ZRANGE', KEYS[i], 0, 0, 'WITHSCORES')
        return {i, math.max(1, tonumber(oldest[2]) + 60000 - now)}
    end
end
if redis.call('ZCARD', KEYS[3]) >= tonumber(ARGV[3]) then
    local oldest = redis.call('ZRANGE', KEYS[3], 0, 0, 'WITHSCORES')
    return {3, math.max(1, tonumber(oldest[2]) - now)}
end
for i = 1, 2 do
    redis.call('ZADD', KEYS[i], now, ARGV[5])
    redis.call('PEXPIRE', KEYS[i], 61000)
end
redis.call('ZADD', KEYS[3], now + tonumber(ARGV[4]), ARGV[5])
redis.call('PEXPIRE', KEYS[3], tonumber(ARGV[4]) + 1000)
return {0, 0}
