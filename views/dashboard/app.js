const bridge = window.AstrBotPluginView;

const SCRIPT_CODE = `(function(){
  try {
    var raw = localStorage.getItem('userToken');
    if (!raw) {
      console.error('❌ 未找到 userToken，请确认已在当前网页登录账号！');
      alert('未找到登录态，请先登录 DeepSeek 平台！');
      return;
    }
    var token = JSON.parse(raw).value;
    if (!token) {
      console.error('❌ userToken 字段为空，请重新登录！');
      return;
    }
    if (typeof copy === 'function') {
      copy(token);
    } else {
      var t = document.createElement('textarea');
      t.value = token;
      document.body.appendChild(t);
      t.select();
      document.execCommand('copy');
      document.body.removeChild(t);
    }
    console.log('%c✅ Token 提取成功并已复制到剪贴板！', 'color: #10b981; font-size: 16px; font-weight: bold;');
    console.log('%cToken 内容: ' + token, 'color: #6366f1;');
    alert('✅ DeepSeek 平台 Token 已复制到剪贴板！\n请回到 AstrBot 控制台页面粘贴保存。');
  } catch(e) {
    console.error('❌ 提取发生异常: ' + e.message);
  }
})();`;

// DOM 元素
const copyScriptBtn = document.getElementById("copy-script-btn");
const copyBtnText = document.getElementById("copy-btn-text");
const toggleCodeBtn = document.getElementById("toggle-code-btn");
const codePreview = document.getElementById("code-preview");
const refreshBtn = document.getElementById("refresh-btn");
const testBtn = document.getElementById("test-btn");
const saveBtn = document.getElementById("save-btn");
const configForm = document.getElementById("config-form");
const apiKeyInput = document.getElementById("conf-api-key");
const tokenInput = document.getElementById("conf-platform-token");
const toastEl = document.getElementById("toast");

// 数据面板元素
const accountStatus = document.getElementById("account-status");
const valTotalBalance = document.getElementById("val-total-balance");
const valBalanceDetail = document.getElementById("val-balance-detail");
const valCostTotal = document.getElementById("val-cost-total");
const valCostAvg = document.getElementById("val-cost-avg");
const valCostPeak = document.getElementById("val-cost-peak");
const valCostPeakDate = document.getElementById("val-cost-peak-date");
const costTableBody = document.getElementById("cost-table-body");

// 初始化脚本预览
codePreview.textContent = SCRIPT_CODE;

// Toast 提示函数
let toastTimer = null;
function showToast(message, type = "success", duration = 4500) {
  if (toastTimer) clearTimeout(toastTimer);
  toastEl.textContent = message;
  toastEl.className = `toast show toast-${type}`;
  toastTimer = setTimeout(() => {
    toastEl.className = "toast";
  }, duration);
}

// 复制脚本事件
copyScriptBtn.addEventListener("click", async () => {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(SCRIPT_CODE);
    } else {
      const ta = document.createElement("textarea");
      ta.value = SCRIPT_CODE;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }

    // 按钮反馈
    copyScriptBtn.classList.add("copied");
    copyBtnText.textContent = "已复制到剪贴板！";
    setTimeout(() => {
      copyScriptBtn.classList.remove("copied");
      copyBtnText.textContent = "一键复制控制台提取脚本";
    }, 2500);

    // 友好提示弹窗与通知
    showToast(
      "📋 脚本已复制！请打开 platform.deepseek.com 按 F12 在 Console 控制台粘贴并回车，Token 会自动存入剪贴板！",
      "success",
      6000
    );
  } catch (err) {
    showToast("复制失败，请点击「查看脚本内容」手动全选复制", "error");
  }
});

// 查看脚本折叠切换
toggleCodeBtn.addEventListener("click", () => {
  const isShow = codePreview.classList.toggle("show");
  toggleCodeBtn.textContent = isShow ? "🙈 隐藏脚本内容" : "👁️ 查看脚本内容";
});

// 密码框明文切换
document.querySelectorAll(".toggle-eye").forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetId = btn.getAttribute("data-target");
    const input = document.getElementById(targetId);
    if (!input) return;
    if (input.type === "password") {
      input.type = "text";
      btn.textContent = "🔒";
    } else {
      input.type = "password";
      btn.textContent = "👁️";
    }
  });
});

// 加载状态
async function loadStatus() {
  accountStatus.textContent = "正在同步数据...";
  accountStatus.style.color = "var(--text-muted)";
  try {
    const data = await bridge.apiGet("status");
    if (!data) return;

    // 填充配置输入框（如果尚未被用户编辑）
    if (data.config) {
      apiKeyInput.value = data.config.deepseek_api_key || "";
      tokenInput.value = data.config.platform_token || "";
    }

    // 渲染余额
    if (data.balance) {
      const b = data.balance;
      accountStatus.textContent = b.is_available ? "✅ 账户状态正常" : "❌ 账户欠费或异常";
      accountStatus.style.color = b.is_available ? "var(--success)" : "var(--danger)";

      if (b.info && b.info.length > 0) {
        const item = b.info[0];
        valTotalBalance.textContent = `¥${Number(item.total_balance || 0).toFixed(2)}`;
        valBalanceDetail.textContent = `充值: ¥${Number(item.topped_up_balance || 0).toFixed(2)} | 赠金: ¥${Number(item.granted_balance || 0).toFixed(2)}`;
      }
    } else {
      accountStatus.textContent = data.config?.deepseek_api_key ? "⚠️ 余额获取失败" : "⚠️ 未配置 API Key";
      accountStatus.style.color = "var(--warning)";
      valTotalBalance.textContent = "-";
      valBalanceDetail.textContent = "请配置有效 API Key 后刷新";
    }

    // 渲染花费统计
    if (data.cost && data.cost.daily) {
      const daily = data.cost.daily;
      const total = Number(data.cost.total || 0);
      const avg = Number(data.cost.avg || 0);
      const peak = data.cost.peak || "-";
      const peakVal = Number(data.cost.peak_val || 0);

      valCostTotal.textContent = `¥${total.toFixed(4)}`;
      valCostAvg.textContent = `日均: ¥${avg.toFixed(4)}`;
      valCostPeak.textContent = `¥${peakVal.toFixed(4)}`;
      valCostPeakDate.textContent = `日期: ${peak}`;

      // 渲染表格
      const dates = Object.keys(daily);
      if (dates.length === 0) {
        costTableBody.innerHTML = '<tr><td colspan="3" style="text-align:center">暂无花费记录</td></tr>';
      } else {
        const maxVal = Math.max(...Object.values(daily), 0.0001);
        let html = "";
        for (const [date, val] of Object.entries(daily)) {
          const num = Number(val);
          const percent = Math.min(100, Math.round((num / maxVal) * 100));
          html += `
            <tr>
              <td style="font-weight:600">${date}</td>
              <td>¥${num.toFixed(4)}</td>
              <td>
                <div class="cost-bar-outer" title="${num.toFixed(4)} CNY">
                  <div class="cost-bar-inner" style="width: ${percent}%"></div>
                </div>
              </td>
            </tr>
          `;
        }
        costTableBody.innerHTML = html;
      }
    } else {
      valCostTotal.textContent = "-";
      valCostAvg.textContent = "请配置 Token 后刷新";
      valCostPeak.textContent = "-";
      valCostPeakDate.textContent = "-";
      costTableBody.innerHTML = `<tr><td colspan="3" style="text-align:center; color:var(--text-muted)">${data.config?.platform_token ? "获取近七天花费失败（Token 可能已失效）" : "尚未配置 Platform Token"}</td></tr>`;
    }
  } catch (err) {
    showToast(`获取状态失败: ${err.message}`, "error");
  }
}

// 刷新按钮
refreshBtn.addEventListener("click", async () => {
  await loadStatus();
  showToast("数据已刷新", "success", 2000);
});

// 保存配置
configForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  saveBtn.disabled = true;
  saveBtn.textContent = "正在保存...";
  try {
    const payload = {
      deepseek_api_key: apiKeyInput.value.trim(),
      platform_token: tokenInput.value.trim(),
    };
    const res = await bridge.apiPost("config/save", payload);
    showToast("✅ 凭据保存成功！配置已更新生效。", "success");
    await loadStatus();
  } catch (err) {
    showToast(`保存失败: ${err.message}`, "error");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = "💾 保存凭据";
  }
});

// 测试连接按钮
testBtn.addEventListener("click", async () => {
  testBtn.disabled = true;
  testBtn.textContent = "正在测试连接...";
  try {
    const payload = {
      deepseek_api_key: apiKeyInput.value.trim(),
      platform_token: tokenInput.value.trim(),
    };
    const res = await bridge.apiPost("test", payload);
    if (res.balance_ok && res.cost_ok) {
      showToast("🎉 测试通过！API Key 余额接口与 Platform Token 花费接口均正常！", "success", 5000);
    } else if (res.balance_ok && !res.cost_ok) {
      showToast(`⚠️ API Key 正常，但 Platform Token 验证失败: ${res.cost_error || "401 过期"}`, "error", 6000);
    } else if (!res.balance_ok && res.cost_ok) {
      showToast(`⚠️ Platform Token 正常，但 API Key 验证失败: ${res.balance_error}`, "error", 6000);
    } else {
      showToast(`❌ 测试全部失败: Key: ${res.balance_error || "异常"} | Token: ${res.cost_error || "异常"}`, "error", 6000);
    }
    await loadStatus();
  } catch (err) {
    showToast(`测试请求异常: ${err.message}`, "error");
  } finally {
    testBtn.disabled = false;
    testBtn.textContent = "⚡ 测试连接并验证";
  }
});

// 页面初始化
(async () => {
  try {
    await bridge.ready();
    await loadStatus();
  } catch (err) {
    console.error("Bridge ready failed:", err);
  }
})();
