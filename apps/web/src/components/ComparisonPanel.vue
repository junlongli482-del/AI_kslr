<script setup lang="ts">
defineProps<{report:any}>()
defineEmits<{choose:[channel:string]}>()
const channelName=(s:string)=>({low:'低价GPT',stable:'稳定GPT',deepseek:'DeepSeek Flash'}[s]||s)
const state=(s:string)=>({running:'处理中',success:'已完成',failed:'失败'}[s]||s)
</script>
<template>
  <details class="comparison-panel" v-if="report?.candidates?.length" open>
    <summary>多模型对比 · 各候选独立处理、分别计费</summary>
    <div class="comparison-scroll"><table><thead><tr><th>模型渠道</th><th>状态 / 耗时</th><th>结果检查</th><th>费用</th><th>操作</th></tr></thead>
      <tbody><tr v-for="c in report.candidates" :key="c.channel"><td>{{channelName(c.channel)}}<small>{{c.model}}</small></td>
        <td>{{state(c.status)}} · {{c.seconds ?? Math.max(0,Math.floor(Date.now()/1000-c.started_at))}}秒</td>
        <td><template v-if="c.quality">{{c.quality.questions}}题 · {{c.quality.missing_answers}}题缺答案 · {{c.quality.missing_regions}}题缺框</template><span v-else>{{c.error?.detail||'等待模型响应'}}</span></td>
        <td>{{c.cost_cny===undefined?'待返回usage':`¥${Number(c.cost_cny).toFixed(5)}`}}<small>{{c.cost_status==='calculated'?'按usage计算':'估算 / 部分费用未知'}}</small></td>
        <td><button class="text-button" v-if="c.status==='success'" @click="$emit('choose',c.channel)">使用此结果</button></td></tr></tbody></table></div>
    <p class="muted">题量和缺项属于机械检查，不代表内容准确率。人工审核前请对照原卷；DeepSeek时段价为估算，失败请求的最终费用以供应商账单为准。</p>
  </details>
</template>
