// Grid Service Bot — group chat and group notice delivery (OpenSim)
// Place in the same object as GridServiceBot.lsl.
// Bot must be a member/officer of the target group with notice permissions.

integer LINK_GROUP = 90210;

string PORTAL_URL = "";
string BOT_TOKEN = "";
integer VERBOSE = TRUE;

integer gConfigLine = 0;
key gNotecardQuery = NULL_KEY;

ack_message(string msgId, integer success, string error)
{
    if (PORTAL_URL == "" || BOT_TOKEN == "") return;
    string url = PORTAL_URL + "/api/bot/ack/" + msgId + "?format=text&token=" + llEscapeURL(BOT_TOKEN);
    url += "&success=" + (string)success;
    if (error != "") url += "&error=" + llEscapeURL(error);
    llHTTPRequest(url, [
        HTTP_METHOD, "GET",
        HTTP_CUSTOM_HEADER, "X-Grid-Bot-Token", BOT_TOKEN
    ], "");
}

start_read_config()
{
    gConfigLine = 0;
    gNotecardQuery = llGetNotecardLine("GridBotConfig", gConfigLine);
}

process_group_line(string line)
{
    list p = llParseString2List(line, ["|"], []);
    if (llGetListLength(p) < 8) return;

    string msgId = llList2String(p, 0);
    string msgType = llList2String(p, 1);
    string groupUuid = llList2String(p, 4);
    string delivery = llList2String(p, 5);
    string subject = llList2String(p, 6);
    string msgBody = llList2String(p, 7);

    if (groupUuid == "" || llStringLength(groupUuid) < 36)
    {
        ack_message(msgId, FALSE, "missing_group");
        return;
    }

    key groupKey = (key)groupUuid;
    integer ok = TRUE;
    string err = "";

    if (delivery == "group_notice")
    {
        if (subject == "") subject = "Grid Event";
        // OpenSim: osGroupNotice(group, subject, message)
        osGroupNotice(groupKey, subject, msgBody);
        if (VERBOSE) llOwnerSay("Group notice [" + msgType + "]: " + subject);
    }
    else
    {
        // OpenSim: llInstantMessageGroup(group, message)
        llInstantMessageGroup(groupKey, msgBody);
        if (VERBOSE) llOwnerSay("Group chat [" + msgType + "]");
    }

    ack_message(msgId, ok, err);
}

default
{
    state_entry()
    {
        if (llGetInventoryType("GridBotConfig") != INVENTORY_NOTECARD)
        {
            llOwnerSay("GridServiceBotGroup: Missing notecard 'GridBotConfig'.");
            return;
        }
        start_read_config();
    }

    dataserver(key query_id, string data)
    {
        if (query_id != gNotecardQuery) return;

        if (data == EOF)
        {
            llOwnerSay("GridServiceBotGroup: Ready for group deliveries.");
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
                else if (k == "VERBOSE") VERBOSE = (llToLower(v) == "1" || llToLower(v) == "true");
            }
        }
        gConfigLine++;
        gNotecardQuery = llGetNotecardLine("GridBotConfig", gConfigLine);
    }

    link_message(integer sender, integer num, string line, key id)
    {
        if (num != LINK_GROUP) return;
        process_group_line(line);
    }
}
