package com.github.tvbox.osc.ui.dialog;

import android.content.Context;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;

import com.github.tvbox.osc.R;

import org.jetbrains.annotations.NotNull;

public class LiveSourceEditDialog extends BaseDialog {
    private EditText etName;
    private EditText etUrl;
    private TextView tvTitle;
    private TextView btnConfirm;
    private OnEditListener listener;
    private String editName;
    private String editUrl;

    public LiveSourceEditDialog(@NonNull @NotNull Context context) {
        super(context, R.style.CustomDialogStyleDim);
        setContentView(R.layout.dialog_live_source_edit);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        tvTitle = findViewById(R.id.tvTitle);
        etName = findViewById(R.id.etName);
        etUrl = findViewById(R.id.etUrl);
        btnConfirm = findViewById(R.id.btnConfirm);

        if (editName != null) {
            tvTitle.setText("编辑直播源");
            etName.setText(editName);
            etUrl.setText(editUrl);
        } else {
            tvTitle.setText("新增直播源");
        }

        etUrl.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override
            public boolean onEditorAction(TextView v, int actionId, KeyEvent event) {
                if (actionId == EditorInfo.IME_ACTION_DONE
                        || (event != null && event.getKeyCode() == KeyEvent.KEYCODE_ENTER)) {
                    doConfirm();
                    return true;
                }
                return false;
            }
        });

        findViewById(R.id.btnCancel).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                dismiss();
            }
        });

        btnConfirm.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                doConfirm();
            }
        });
    }

    private void doConfirm() {
        String name = etName.getText().toString().trim();
        String url = etUrl.getText().toString().trim();
        if (TextUtils.isEmpty(name)) {
            Toast.makeText(getContext(), "请输入名称", Toast.LENGTH_SHORT).show();
            return;
        }
        if (TextUtils.isEmpty(url)) {
            Toast.makeText(getContext(), "请输入网址", Toast.LENGTH_SHORT).show();
            return;
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            Toast.makeText(getContext(), "网址需以http://或https://开头", Toast.LENGTH_SHORT).show();
            return;
        }
        if (listener != null) {
            listener.onConfirm(name, url);
        }
        dismiss();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getAction() == KeyEvent.ACTION_DOWN) {
            int keyCode = event.getKeyCode();
            if (keyCode == KeyEvent.KEYCODE_DPAD_DOWN) {
                View focusedView = getCurrentFocus();
                if (focusedView != null && focusedView.getId() == R.id.etUrl) {
                    if (btnConfirm != null) {
                        btnConfirm.requestFocus();
                        return true;
                    }
                }
            }
        }
        return super.dispatchKeyEvent(event);
    }

    public void setEditData(String name, String url) {
        this.editName = name;
        this.editUrl = url;
    }

    public void setOnEditListener(OnEditListener listener) {
        this.listener = listener;
    }

    public interface OnEditListener {
        void onConfirm(String name, String url);
    }
}