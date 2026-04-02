document.addEventListener("DOMContentLoaded", () => {
    const datePicker = document.getElementById("date-picker");
    if (datePicker) {
        datePicker.addEventListener("change", (e) => {
            window.location.href = `/?date=${e.target.value}`;
        });
    }

    const setupForm = document.getElementById("setup-form");
    if (setupForm) {
        setupForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const msg = document.getElementById("setup-msg");
            const data = {
                llm_api_key: document.getElementById("api_key").value,
                llm_base_url: document.getElementById("base_url").value,
                llm_model: document.getElementById("model").value,
            };
            msg.textContent = "保存中...";
            msg.className = "msg";
            try {
                const resp = await fetch("/api/setup", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                });
                if (resp.ok) {
                    msg.textContent = "配置已保存！正在跳转...";
                    msg.className = "msg success";
                    setTimeout(() => window.location.href = "/", 1500);
                } else {
                    const err = await resp.json();
                    msg.textContent = "错误: " + (err.detail || "保存失败");
                    msg.className = "msg error";
                }
            } catch (err) {
                msg.textContent = "网络错误: " + err.message;
                msg.className = "msg error";
            }
        });
    }
});

async function fetchPapers(date) {
    const msg = document.getElementById("fetch-msg");
    if (msg) {
        msg.textContent = "正在抓取论文...";
        msg.className = "msg";
    }
    try {
        const resp = await fetch(`/api/fetch?date=${date}`, { method: "POST" });
        if (resp.ok) {
            const data = await resp.json();
            if (data.fetched > 0) {
                if (msg) {
                    msg.textContent = `成功抓取 ${data.fetched} 篇论文！正在刷新...`;
                    msg.className = "msg success";
                }
                setTimeout(() => window.location.reload(), 1500);
            } else {
                if (msg) {
                    msg.textContent = "该日期暂无论文数据";
                    msg.className = "msg";
                }
            }
        } else {
            const err = await resp.json();
            if (msg) {
                msg.textContent = "抓取失败: " + (err.detail || "未知错误");
                msg.className = "msg error";
            }
        }
    } catch (err) {
        if (msg) {
            msg.textContent = "网络错误: " + err.message;
            msg.className = "msg error";
        }
    }
}

async function syncPapers(date) {
    const msg = document.getElementById("fetch-msg");
    try {
        const resp = await fetch(`/api/fetch?date=${date}`, { method: "POST" });
        if (resp.ok) {
            const data = await resp.json();
            if (data.inserted > 0) {
                // 有新增论文，刷新页面
                if (msg) {
                    msg.textContent = `发现 ${data.inserted} 篇新论文，正在刷新...`;
                    msg.className = "msg success";
                }
                setTimeout(() => window.location.reload(), 800);
            } else if (data.fetched === 0 && msg) {
                // HF API 该日期无论文
                msg.textContent = "该日期暂无论文数据";
                msg.className = "msg";
            }
            // fetched > 0 但 inserted === 0 表示没有新增，不做任何事
        } else {
            if (msg) {
                const err = await resp.json();
                msg.textContent = "同步失败: " + (err.detail || "未知错误");
                msg.className = "msg error";
            }
        }
    } catch (err) {
        if (msg) {
            msg.textContent = "网络错误: " + err.message;
            msg.className = "msg error";
        }
    }
}

async function resummarize(paperId) {
    try {
        const resp = await fetch(`/api/resummarize/${paperId}`, { method: "POST" });
        if (resp.ok) {
            window.location.reload();
        } else {
            alert("摘要生成失败，请稍后重试");
        }
    } catch (err) {
        alert("网络错误: " + err.message);
    }
}

async function regenerateBrief(paperId, btn) {
    const container = document.getElementById(`brief-${paperId}`);
    const summaryEl = container.querySelector("p");
    if (summaryEl) {
        summaryEl.textContent = "概要重新生成中...";
        summaryEl.className = "summary-pending";
    }
    btn.disabled = true;
    try {
        const resp = await fetch(`/api/regenerate_brief/${paperId}`, { method: "POST" });
        if (resp.ok) {
            const data = await resp.json();
            if (summaryEl) {
                summaryEl.textContent = data.summary;
                summaryEl.className = "";
            }
        } else {
            if (summaryEl) {
                summaryEl.textContent = "概要生成失败";
                summaryEl.className = "summary-failed";
            }
        }
    } catch (err) {
        if (summaryEl) {
            summaryEl.textContent = "网络错误: " + err.message;
            summaryEl.className = "summary-failed";
        }
    }
    btn.disabled = false;
}
