local url_count = 0
local wretch_username = os.getenv("wretch_username")


wget.callbacks.download_child_p = function(urlpos, parent, depth, start_url_parsed, iri, verdict, reason)
  local url = urlpos["url"]["url"]

  -- Don't go outside our username
  if string.match(url, "wretch%.cc") then
    if not (
    string.match(url, "wretch%.cc/[a-z0-9A-Z]-/"..wretch_username.."$") or
    string.match(url, "wretch%.cc/[a-z0-9A-Z]-/"..wretch_username.."/") or
    string.match(url, "id="..wretch_username.."$") or
    string.match(url, "id="..wretch_username.."&")
    ) then
      verdict = false
    end
  end

  if string.match(url, "wretch%.cc/help/prosecute.php") then
    verdict = false
  end

  -- already in wayback machine
  if string.match(url, "cosmos%.bcst%.yahoo%.com/player/media/swf/FLVVideoSolo%.swf") then
    return false
  end

  return verdict
end

-- The number of times we'll retry requests with code >= 500 and <= 599.
-- If this hits zero, we skip the URL, reset the counter, and go to the next
-- one.
local retry_counter = 5

wget.callbacks.httploop_result = function(url, err, http_stat)
  local sleep_time = 60
  local status_code = http_stat["statcode"]

  if status_code >= 500 then
    -- issue #1, skip broken web server
    if status_code == 502 and string.match(url["url"], "d%.yimg%.com") then
      io.stdout:write("(d.yimg.com skip)\n")
      io.stdout:flush()
      return wget.actions.EXIT
    end

    if status_code <= 599 then
      retry_counter = retry_counter - 1
    end

    if retry_counter <= 0 then
      io.stdout:write("Skipping "..url["url"].." due to too many failures.\n")
      io.stdout:flush()
      retry_counter = 5
      return wget.actions.EXIT
    else
      io.stdout:write("\nYahoo!!! (code "..http_stat.statcode.."). Sleeping for ".. sleep_time .." seconds.  Will retry "..retry_counter.." more times.\n")
      io.stdout:flush()

      -- Note that wget has its own linear backoff to this time as well
      os.execute("sleep " .. sleep_time)
      return wget.actions.CONTINUE
    end
  else
    -- We're okay; sleep a bit (if we have to) and continue
    local sleep_time = 0.1 * (math.random(75, 125) / 100.0)

    if string.match(url["url"], "yimg%.com") then
      -- We should be able to go fast on images since that's what a web browser does
      sleep_time = 0
    end

    if sleep_time > 0.001 then
      os.execute("sleep " .. sleep_time)
    end

    tries = 0
    return wget.actions.NOTHING
  end
end

wget.callbacks.get_urls = function(file, url, is_css, iri)
  -- progress message
  url_count = url_count + 1
  if url_count % 2 == 0 then
    io.stdout:write("\r - Downloaded "..url_count.." URLs.")
    io.stdout:flush()
  end
end

wget.callbacks.lookup_host = function(host)
  if string.match(host, "wretch%.cc") then
    local table = {"203.84.197.27", "203.84.197.26"}
    return table[ math.random( #table ) ]
  else
    -- use normal DNS ip
    return nil
  end
end
