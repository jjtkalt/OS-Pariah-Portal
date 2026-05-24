// Grid Service Bot — OS Pariah Portal message delivery
// Place in a dedicated bot avatar on your grid's announce region.
// Requires notecard "GridBotConfig" (see GridBotConfig.example.txt).
// Add GridServiceBotGroup.lsl in the same object for group chat/notices.
//
// Polls GET /api/bot/queue?format=text and delivers IM or region chat.
// Acknowledges via GET /api/bot/ack/<id>?format=text&token=...

integer LINK_GROUP = 90210;

string PORTAL_URL = "";
string BOT_TOKEN = "";
integer POLL_INTERVAL = 30;
integer ANNOUNCE_CHANNEL = 0;
integer VERBOSE = TRUE;

key gPollRequest = NULL_KEY;
integer gPolling = FALSE;
integer gConfigLine = 0;
key gNotecardQuery = NULL_KEY;

ack_message(string msgId, integer success, string error)
{
    string url = PORTAL_URL + "/api/bot/ack/" + msgId + "?format=text&token=" + llEscapeURL(BOT_TOKEN);
    url += "&success=" + (string)success;
    if (error != "") url += "&error=" + llEscapeURL(error);
    llHTTPRequest(url, [
        HTTP_METHOD, "GET",
        HTTP_CUSTOM_HEADER, "X-Grid-Bot-Token", BOT_TOKEN
    ], "");
}

process_message_line(string line)
{
    list p = llParseString2List(line, ["|"], []);
    integer n = llGetListLength(p);
    if (n < 5) return;

    string msgId = llList2String(p, 0);
    string msgType = llList2String(p, 1);
    string targetUuid = llList2String(p, 2);
    string regionName = llList2String(p, 3);
    string groupUuid = "";
    string delivery = "region";
    string subject = "";
    string msgBody = "";

    if (n >= 8)
    {
        groupUuid = llList2String(p, 4);
        delivery = llList2String(p, 5);
        subject = llList2String(p, 6);
        msgBody = llList2String(p, 7);
    }
    else
    {
        msgBody = llList2String(p, 4);
        if (targetUuid != "" && llStringLength(targetUuid) >= 36)
            delivery = "im";
    }

    if (delivery == "group_chat" || delivery == "group_notice")
    {
        llMessageLinked(LINK_SET, LINK_GROUP, line, NULL_KEY);
        return;
    }

    integer ok = TRUE;
    string err = "";

    if (delivery == "im" || (targetUuid != "" && llStringLength(targetUuid) >= 36))
    {
        llInstantMessage(targetUuid, msgBody);
        if (VERBOSE) llOwnerSay("IM [" + msgType + "]");
    }
    else
    {
        string here = llGetRegionName();
        if (regionName != "" && llToLower(regionName) != llToLower(here))
        {
            ok = FALSE;
            err = "wrong_region";
            if (VERBOSE) llOwnerSay("Skip [" + msgType + "]: needs " + regionName);
        }
        else
        {
            llSay(ANNOUNCE_CHANNEL, msgBody);
            if (VERBOSE) llOwnerSay("Say [" + msgType + "]: " + llGetSubString(msgBody, 0, 50));
        }
    }
    ack_message(msgId, ok, err);
}

poll_queue()
{
    if (PORTAL_URL == "" || BOT_TOKEN == "") return;
    if (gPolling) return;
    gPolling = TRUE;
    string url = PORTAL_URL + "/api/bot/queue?format=text&token=" + llEscapeURL(BOT_TOKEN);
    gPollRequest = llHTTPRequest(url, [
        HTTP_METHOD, "GET",
        HTTP_MIMETYPE, "text/plain",
        HTTP_CUSTOM_HEADER, "X-Grid-Bot-Token", BOT_TOKEN
    ], "");
}

start_read_config()
{
    gConfigLine = 0;
    gNotecardQuery = llGetNotecardLine("GridBotConfig", gConfigLine);
}

default
{
    state_entry()
    {
        llSetTimerEvent(0.0);
        if (llGetInventoryType("GridBotConfig") != INVENTORY_NOTECARD)
        {
            llOwnerSay("GridServiceBot: Missing notecard 'GridBotConfig'.");
            return;
        }
        start_read_config();
    }

    dataserver(key query_id, string data)
    {
        if (query_id != gNotecardQuery) return;

        if (data == EOF)
        {
            if (PORTAL_URL == "" || BOT_TOKEN == "")
            {
                llOwnerSay("GridServiceBot: PORTAL_URL and BOT_TOKEN required.");
                return;
            }
            llOwnerSay("GridServiceBot: Polling every " + (string)POLL_INTERVAL + "s.");
            llSetTimerEvent((float)POLL_INTERVAL);
            poll_queue();
            return;
        }

        data = llStringTrim(data, STRING_TRIM);
        if (data != "" && llSubStringIndex(data, "#") != 0)
        {
            integer eq = llSubStringIndex(data, "=");
            if (eq > 0)
            {
                string k = llToUpper(llStringTrim(llGetSubString(data, 0, eq - 1), STRING_TRIM));
                string v = llStringTrim(llGetSubString(data, eq + 1, -1), STRING_TRIM);
                if (k == "PORTAL_URL") PORTAL_URL = v;
                else if (k == "BOT_TOKEN") BOT_TOKEN = v;
                else if (k == "POLL_INTERVAL") POLL_INTERVAL = (integer)v;
                else if (k == "ANNOUNCE_CHANNEL") ANNOUNCE_CHANNEL = (integer)v;
                else if (k == "VERBOSE") VERBOSE = (llToLower(v) == "1" || llToLower(v) == "true");
            }
        }
        gConfigLine++;
        gNotecardQuery = llGetNotecardLine("GridBotConfig", gConfigLine);
    }

    timer()
    {
        if (!gPolling) poll_queue();
    }

    touch_start(integer total_number)
    {
        llOwnerSay("Manual poll.");
        poll_queue();
    }

    http_response(key request_id, integer status, list metadata, string body)
    {
        if (request_id != gPollRequest) return;
        gPolling = FALSE;
        if (status != 200)
        {
            llOwnerSay("Poll failed HTTP " + (string)status);
            return;
        }
        if (llStringTrim(body, STRING_TRIM) == "")
        {
            if (VERBOSE) llOwnerSay("Queue empty.");
            return;
        }
        list lines = llParseString2List(body, ["\n"], []);
        integer i;
        integer count = llGetListLength(lines);
        for (i = 0; i < count; ++i)
        {
            string line = llStringTrim(llList2String(lines, i), STRING_TRIM);
            if (line != "") process_message_line(line);
        }
    }
}
