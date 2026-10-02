package com.github.tvbox.osc.bean;

import android.util.Log;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;
import com.orhanobut.hawk.Hawk;

import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LiveSourceManager {
    private static final String TAG = "LiveSourceManager";
    private static final String KEY_LIVE_SOURCE_LIST = "live_source_list";
    private static final String KEY_CURRENT_LIVE_SOURCE = "current_live_source_name";
    private static final String LOCAL_SOURCE_NAME = "本地直播";
    private static LiveSourceManager instance;
    private final Gson gson = new Gson();

    private LiveSourceManager() {
    }

    public static LiveSourceManager get() {
        if (instance == null) {
            instance = new LiveSourceManager();
        }
        return instance;
    }

    public List<LiveSourceItem> getSourceList() {
        String json = Hawk.get(KEY_LIVE_SOURCE_LIST, "");
        Log.d(TAG, "getSourceList: json length=" + json.length() + " json=" + (json.length() > 100 ? json.substring(0, 100) + "..." : json));
        if (json.isEmpty()) {
            List<LiveSourceItem> defaultList = getDefaultSources();
            saveSourceList(defaultList);
            Log.d(TAG, "getSourceList: json was empty, returning " + defaultList.size() + " default sources");
            return defaultList;
        }
        List<LiveSourceItem> list = null;
        try {
            Type listType = new TypeToken<ArrayList<LiveSourceItem>>() {}.getType();
            list = gson.fromJson(json, listType);
        } catch (Exception e) {
            Log.e(TAG, "getSourceList: parse error", e);
        }
        if (list == null || list.isEmpty()) {
            List<LiveSourceItem> defaultList = getDefaultSources();
            saveSourceList(defaultList);
            Log.d(TAG, "getSourceList: parsed list was null/empty, returning " + defaultList.size() + " default sources");
            return defaultList;
        }
        ensureLocalSourceExists(list);
        Log.d(TAG, "getSourceList: returning " + list.size() + " sources from storage");
        return list;
    }

    private void ensureLocalSourceExists(List<LiveSourceItem> list) {
        for (LiveSourceItem item : list) {
            if (LOCAL_SOURCE_NAME.equals(item.getName()) && item.isLocal()) {
                return;
            }
        }
        LiveSourceItem localSource = new LiveSourceItem(LOCAL_SOURCE_NAME, LiveSourceItem.TYPE_LOCAL, new ArrayList<LiveSourceItem.LocalChannel>());
        list.add(0, localSource);
        saveSourceList(list);
    }

    public List<LiveSourceItem> getOnlineSources() {
        List<LiveSourceItem> all = getSourceList();
        List<LiveSourceItem> online = new ArrayList<>();
        for (LiveSourceItem item : all) {
            if (!item.isLocal()) {
                online.add(item);
            }
        }
        return online;
    }

    public LiveSourceItem getLocalSource() {
        List<LiveSourceItem> list = getSourceList();
        for (LiveSourceItem item : list) {
            if (LOCAL_SOURCE_NAME.equals(item.getName()) && item.isLocal()) {
                return item;
            }
        }
        LiveSourceItem localSource = new LiveSourceItem(LOCAL_SOURCE_NAME, LiveSourceItem.TYPE_LOCAL, new ArrayList<LiveSourceItem.LocalChannel>());
        list.add(0, localSource);
        saveSourceList(list);
        return localSource;
    }

    public boolean syncLocalChannels(String jsonData) {
        Log.d(TAG, "syncLocalChannels: received json length=" + (jsonData != null ? jsonData.length() : 0));
        if (jsonData == null || jsonData.isEmpty()) {
            Log.w(TAG, "syncLocalChannels: empty data");
            return false;
        }
        try {
            JsonObject root = JsonParser.parseString(jsonData).getAsJsonObject();
            JsonArray livesArr = root.getAsJsonArray("lives");
            if (livesArr == null) {
                Log.w(TAG, "syncLocalChannels: no 'lives' array in json");
                return false;
            }
            List<LiveSourceItem.LocalChannel> channels = new ArrayList<>();
            for (JsonElement elem : livesArr) {
                JsonObject chObj = elem.getAsJsonObject();
                String name = chObj.has("name") ? chObj.get("name").getAsString() : "";
                List<String> urls = new ArrayList<>();
                if (chObj.has("urls")) {
                    JsonArray urlsArr = chObj.getAsJsonArray("urls");
                    for (JsonElement urlElem : urlsArr) {
                        urls.add(urlElem.getAsString());
                    }
                }
                if (!name.isEmpty() && !urls.isEmpty()) {
                    channels.add(new LiveSourceItem.LocalChannel(name, urls));
                }
            }
            List<LiveSourceItem> list = getSourceList();
            for (LiveSourceItem item : list) {
                if (LOCAL_SOURCE_NAME.equals(item.getName()) && item.isLocal()) {
                    item.setChannels(channels);
                    saveSourceList(list);
                    Log.i(TAG, "syncLocalChannels: synced " + channels.size() + " channels");
                    return true;
                }
            }
            LiveSourceItem newLocal = new LiveSourceItem(LOCAL_SOURCE_NAME, LiveSourceItem.TYPE_LOCAL, channels);
            list.add(0, newLocal);
            saveSourceList(list);
            Log.i(TAG, "syncLocalChannels: created new local source with " + channels.size() + " channels");
            return true;
        } catch (Exception e) {
            Log.e(TAG, "syncLocalChannels: parse error", e);
            return false;
        }
    }

    public void saveSourceList(List<LiveSourceItem> list) {
        ensureLocalSourceExists(list);
        Collections.sort(list, (a, b) -> {
            if (a.isLocal() && !b.isLocal()) return -1;
            if (!a.isLocal() && b.isLocal()) return 1;
            return a.compareTo(b);
        });
        String json = gson.toJson(list);
        Hawk.put(KEY_LIVE_SOURCE_LIST, json);
    }

    public void addSource(LiveSourceItem item) {
        List<LiveSourceItem> list = getSourceList();
        for (LiveSourceItem existing : list) {
            if (existing.getName().equals(item.getName())) {
                existing.setUrl(item.getUrl());
                existing.setType(item.getType());
                existing.setChannels(item.getChannels());
                saveSourceList(list);
                return;
            }
        }
        list.add(item);
        saveSourceList(list);
    }

    public void removeSource(LiveSourceItem item) {
        List<LiveSourceItem> list = getSourceList();
        LiveSourceItem toRemove = null;
        for (LiveSourceItem s : list) {
            if (s.getName().equals(item.getName()) && s.getUrl().equals(item.getUrl())) {
                toRemove = s;
                break;
            }
        }
        if (toRemove != null) {
            list.remove(toRemove);
            saveSourceList(list);
        }
    }

    public void updateSource(LiveSourceItem oldItem, LiveSourceItem newItem) {
        List<LiveSourceItem> list = getSourceList();
        for (int i = 0; i < list.size(); i++) {
            LiveSourceItem s = list.get(i);
            if (s.getName().equals(oldItem.getName()) && s.getUrl().equals(oldItem.getUrl())) {
                list.set(i, newItem);
                saveSourceList(list);
                return;
            }
        }
    }

    public void clearAll() {
        Hawk.put(KEY_LIVE_SOURCE_LIST, "");
    }

    public String getCurrentSourceUrl() {
        List<LiveSourceItem> list = getSourceList();
        if (list.isEmpty()) return "";
        String currentName = Hawk.get(KEY_CURRENT_LIVE_SOURCE, "");
        if (currentName.isEmpty()) {
            setCurrentSource(list.get(0));
            return list.get(0).getUrl();
        }
        for (LiveSourceItem item : list) {
            if (item.getName().equals(currentName)) {
                return item.isLocal() ? "local://" + item.getName() : item.getUrl();
            }
        }
        setCurrentSource(list.get(0));
        return list.get(0).isLocal() ? "local://" + list.get(0).getName() : list.get(0).getUrl();
    }

    public void setCurrentSource(LiveSourceItem item) {
        Hawk.put(KEY_CURRENT_LIVE_SOURCE, item.getName());
    }

    public LiveSourceItem getCurrentSource() {
        List<LiveSourceItem> list = getSourceList();
        if (list.isEmpty()) return null;
        String currentName = Hawk.get(KEY_CURRENT_LIVE_SOURCE, "");
        if (currentName.isEmpty()) {
            setCurrentSource(list.get(0));
            return list.get(0);
        }
        for (LiveSourceItem item : list) {
            if (item.getName().equals(currentName)) {
                return item;
            }
        }
        setCurrentSource(list.get(0));
        return list.get(0);
    }

    public String getCurrentSourceName() {
        LiveSourceItem current = getCurrentSource();
        return current != null ? current.getName() : "";
    }

    public List<LiveSourceItem> getDefaultSources() {
        List<LiveSourceItem> list = new ArrayList<>();
        list.add(new LiveSourceItem(LOCAL_SOURCE_NAME, LiveSourceItem.TYPE_LOCAL, new ArrayList<LiveSourceItem.LocalChannel>()));
        list.add(new LiveSourceItem("Guovin(IPv4)", "https://gh-proxy.com/https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u"));
        list.add(new LiveSourceItem("Guovin(IPv6)", "https://gh-proxy.com/https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv6/result.m3u"));
        list.add(new LiveSourceItem("Kimentanm", "https://gh-proxy.com/https://raw.githubusercontent.com/Kimentanm/aptv/master/m3u/iptv.m3u"));
        list.add(new LiveSourceItem("ChinaIPTV", "https://gh-proxy.com/https://raw.githubusercontent.com/hujingguang/ChinaIPTV/main/cnTV_AutoUpdate.m3u8"));
        list.add(new LiveSourceItem("iptv-sources(IPv6)", "https://m3u.ibert.me/fmml_ipv6.m3u"));
        list.add(new LiveSourceItem("myIPTV(IPv6)", "https://gh-proxy.com/https://raw.githubusercontent.com/suxuang/myIPTV/refs/heads/main/ipv6.m3u"));
        list.add(new LiveSourceItem("zwc456baby", "https://gh-proxy.com/https://raw.githubusercontent.com/zwc456baby/iptv_alive/refs/heads/master/live.m3u"));
        list.add(new LiveSourceItem("CandyMu", "https://gitlab.com/noimank/tvbox/-/raw/main/tvbox1.json"));
        list.add(new LiveSourceItem("yingshicang", "http://影视仓.com/"));
        list.add(new LiveSourceItem("Clun在线", "https://clun.top/box.json"));
        list.add(new LiveSourceItem("L佬线路", "https://android.lushunming.qzz.io/json/index.json"));
        list.add(new LiveSourceItem("D佬线路", "http://rihou.cc:555/nzk/nzk0722.json"));
        list.add(new LiveSourceItem("老刘备线路", "https://ghproxy.net/https://raw.githubusercontent.com/liu673cn/box/main/m.json"));
        list.add(new LiveSourceItem("分享者线路", "https://ghproxy.net/https://raw.githubusercontent.com/maoystv/6/main/001.json"));
        list.add(new LiveSourceItem("yw88075", "https://gh-proxy.com/https://raw.githubusercontent.com/yw88075/tvbox/main/pg/jsm.json"));
        list.add(new LiveSourceItem("东篱线路", "https://raw.githubusercontent.com/chitue/dongliTV/main/api.json"));
        list.add(new LiveSourceItem("香雅晴线", "https://gh-proxy.com/https://raw.githubusercontent.com/xyq254245/xyqonlinerule/main/XYQTVBox.json"));
        list.add(new LiveSourceItem("高天流云", "https://gh-proxy.com/https://raw.githubusercontent.com/gaotianliuyun/gao/master/js.json"));
        list.add(new LiveSourceItem("高天流云XYQ", "https://gh-proxy.com/raw.githubusercontent.com/gaotianliuyun/gao/master/XYQ.json"));
        list.add(new LiveSourceItem("饭太硬", "http://fty.xxooo.cf/tv"));
        list.add(new LiveSourceItem("饭太硬推荐", "http://www.饭太硬.cc/tv"));
        list.add(new LiveSourceItem("饭太硬2", "http://www.饭太硬.net/tv"));
        list.add(new LiveSourceItem("饭太硬3", "http://www.饭太硬.art/tv"));
        list.add(new LiveSourceItem("饭太硬4", "http://fty.888484.xyz/tv"));
        list.add(new LiveSourceItem("王二小（网盘4K）", "http://tvbox.王二小放牛娃.top"));
        list.add(new LiveSourceItem("王二小备用", "http://tvbox.xn--4kq62z5rby2qupq9ub.top/"));
        list.add(new LiveSourceItem("王二小（新）", "https://9280.kstore.vip/newwex.json"));
        list.add(new LiveSourceItem("嗷呜备用", "https://9763.kstore.vip/aowu.json"));
        list.add(new LiveSourceItem("哈基米", "https://17264.kstore.space/哈基米.png"));
        list.add(new LiveSourceItem("盒子迷2026", "https://盒子迷.top/禁止贩卖"));
        list.add(new LiveSourceItem("牛二线路", "https://9280.kstore.space/wex.json"));
        list.add(new LiveSourceItem("南风线路", "https://gh-proxy.com/https://raw.githubusercontent.com/yoursmile66/TVBox/refs/heads/main/XC.json"));
        list.add(new LiveSourceItem("金鱼box接口", "http://mzrjk.top/VIP"));
        list.add(new LiveSourceItem("小盒子单仓", "http://xhztv.top/xhz"));
        list.add(new LiveSourceItem("英格里希嗷呜", "http://www.英格里希嗷呜.top/tv"));
        list.add(new LiveSourceItem("宝盒接口", "http://宝盒接口.top"));
        Collections.sort(list);
        return list;
    }
}