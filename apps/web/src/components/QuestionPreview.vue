<script setup lang="ts">
import type {Question} from '../types'
import {renderMarkdown} from '../render'
defineProps<{question:Question}>()
</script>
<template>
  <div class="question-preview">
    <div class="question-prose" v-html="renderMarkdown(question.stem, question.image_layout||{})"/>
    <div class="preview-options" :style="{display:'grid',gridTemplateColumns:`repeat(${question.options_layout?.columns||1},minmax(0,1fr))`,gap:'12px'}">
      <div v-for="option in question.options" :key="option.label" class="question-prose" v-html="renderMarkdown(option.label+'. '+option.content, question.image_layout||{})"/>
    </div>
    <div v-for="(sub,index) in question.subquestions" :key="index" class="preview-subquestion"><div class="question-prose"><strong>{{sub.number}}</strong><span v-html="renderMarkdown(sub.stem, question.image_layout||{})"/></div><div class="preview-options" v-if="sub.options?.length"><div v-for="option in sub.options" :key="option.label" class="question-prose" v-html="renderMarkdown(option.label+'. '+option.content, question.image_layout||{})"/></div><div class="answer-block" v-if="sub.answer?.value"><label>答案 <span v-if="sub.score!=null">· {{sub.score}}分</span></label><div class="question-prose" v-html="renderMarkdown(sub.answer.value, question.image_layout||{})"/><template v-if="sub.answer.analysis"><label>解析</label><div class="question-prose" v-html="renderMarkdown(sub.answer.analysis, question.image_layout||{})"/></template></div></div>
    <div class="answer-block" v-if="!question.subquestions?.length"><label>答案</label><div class="question-prose" v-html="renderMarkdown(question.answer||'待完善', question.image_layout||{})"/><label>解析</label><div class="question-prose" v-html="renderMarkdown(question.analysis||'原资料未提供', question.image_layout||{})"/></div>
    <template v-if="question.attributes.scoring_criteria"><label>评分标准</label><div class="question-prose" v-html="renderMarkdown(question.attributes.scoring_criteria, question.image_layout||{})"/></template>
  </div>
</template>
