package com.github.tvbox.osc.server;

import android.content.Context;
import android.os.Bundle;
import android.text.TextUtils;

import com.github.tvbox.osc.bean.LiveSourceManager;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.HistoryHelper;
import com.github.tvbox.osc.util.LOG;
import com.orhanobut.hawk.Hawk;

import org.greenrobot.eventbus.EventBus;

import java.io.IOException;

import tv.danmaku.ijk.media.player.IjkMediaPlayer;

public class ControlManager {
    private static ControlManager instance;
    private RemoteServer mServer = null;
    private Context mContext;

    private ControlManager() {

    }

    public static ControlManager get() {
        if (instance == null) {
            synchronized (ControlManager.class) {
                if (instance == null) {
                    instance = new ControlManager();
                }
            }
        }
        return instance;
    }

    public static void init(Context context) {
        if (instance == null) {
            instance = new ControlManager();
        }
        instance.mContext = context.getApplicationContext();
        // 应用启动即启动服务器，无需打开远程控制弹窗
        instance.startServer();
    }

    public String getAddress(boolean local) {
        if (mServer == null || !mServer.isStarting()) {
            startServer();
        }
        if (mServer == null || !mServer.isStarting()) {
            return "";
        }
        return local ? mServer.getLoadAddress() : mServer.getServerAddress();
    }

    public synchronized void startServer() {
        if (mServer != null && mServer.isStarting()) {
            return;
        }
        do {
            mServer = new RemoteServer(RemoteServer.serverPort, mContext);
            mServer.setDataReceiver(new DataReceiver() {
                @Override
                public void onTextReceived(String text) {
                }

                @Override
                public void onApiReceived(String url) {
                    EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_API_URL_CHANGE, url));
                }

                @Override
                public void onLiveApiReceived(String url) {
                    if (!TextUtils.isEmpty(url)) {
                        Hawk.put(HawkConfig.LIVE_API_URL, url);
                        HistoryHelper.setLiveApiHistory(url);
                    }
                    EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_LIVE_API_URL_CHANGE, url));
                }

                @Override
                public void onDanmuApiReceived(String url) {
                    Hawk.put(HawkConfig.DANMU_API, TextUtils.isEmpty(url) ? "" : url);
                    EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_SET_DANMU_SETTINGS, false));
                }

                @Override
                public void onPushReceived(String url) {
                    LOG.i("ControlManager: push received url=" + (url != null ? url.substring(0, Math.min(80, url.length())) : "null"));
                    EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_PUSH_URL, url));
                }

                @Override
                public void onStopReceived() {
                    LOG.i("ControlManager: stop received");
                    EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_PUSH_URL, ""));
                }

                @Override
                public void onSeekReceived(long positionMs) {
                    LOG.i("ControlManager: seek received pos=" + positionMs + "ms");
                    EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_SEEK_POSITION, positionMs));
                }

                @Override
                public void onLocalChannelsReceived(String json) {
                    LOG.i("ControlManager: local channels sync received, length=" + (json != null ? json.length() : 0));
                    if (json != null && !json.isEmpty()) {
                        boolean ok = LiveSourceManager.get().syncLocalChannels(json);
                        if (ok) {
                            EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_LOCAL_CHANNELS_SYNC, "success"));
                        }
                    }
                }
            });
            try {
                mServer.start();
                KeepAliveService.start(mContext);
                com.github.catvod.CatvodProxy.set(RemoteServer.serverPort);
                IjkMediaPlayer.setDotPort(Hawk.get(HawkConfig.DOH_URL, 0) > 0, RemoteServer.serverPort);
                break;
            } catch (IOException ex) {
                RemoteServer.serverPort++;
                mServer.stop();
            }
        } while (RemoteServer.serverPort < 9999);
    }

    public void stopServer() {
        if (mServer != null && mServer.isStarting()) {
            mServer.stop();
        }
        mServer = null;
        if (mContext != null) {
            KeepAliveService.stop(mContext);
        }
    }
}