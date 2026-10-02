package com.github.tvbox.osc.bean;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class LiveSourceItem implements Serializable, Comparable<LiveSourceItem> {
    public static final int TYPE_ONLINE = 0;
    public static final int TYPE_LOCAL = 1;

    private String name;
    private String url;
    private int type = TYPE_ONLINE;
    private List<LocalChannel> channels;

    public LiveSourceItem() {
    }

    public LiveSourceItem(String name, String url) {
        this.name = name;
        this.url = url;
        this.type = TYPE_ONLINE;
    }

    public LiveSourceItem(String name, int type, List<LocalChannel> channels) {
        this.name = name;
        this.type = type;
        this.url = "local://" + name;
        this.channels = channels;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public int getType() {
        return type;
    }

    public void setType(int type) {
        this.type = type;
    }

    public List<LocalChannel> getChannels() {
        return channels;
    }

    public void setChannels(List<LocalChannel> channels) {
        this.channels = channels;
    }

    public boolean isLocal() {
        return type == TYPE_LOCAL;
    }

    @Override
    public int compareTo(LiveSourceItem o) {
        if (type != o.type) {
            return o.type - type;
        }
        if (name == null) return 1;
        if (o.name == null) return -1;
        return name.compareTo(o.name);
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (obj == null || getClass() != obj.getClass()) return false;
        LiveSourceItem that = (LiveSourceItem) obj;
        if (type != that.type) return false;
        return name != null && name.equals(that.name);
    }

    @Override
    public int hashCode() {
        int result = name != null ? name.hashCode() : 0;
        result = 31 * result + type;
        return result;
    }

    public static class LocalChannel implements Serializable {
        private String name;
        private List<String> urls;

        public LocalChannel() {
        }

        public LocalChannel(String name, List<String> urls) {
            this.name = name;
            this.urls = urls;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public List<String> getUrls() {
            return urls;
        }

        public void setUrls(List<String> urls) {
            this.urls = urls;
        }
    }
}