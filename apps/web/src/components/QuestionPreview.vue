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
    <div v-for="(sub,index) in question.subquestions" :key="index" class="question-prose preview-subquestion"><strong>{{sub.number}}</strong><div v-html="renderMarkdown(sub.stem, question.image_layout||{})"/></div>
    <div class="answer-block"><label>答案</label><div class="question-prose" v-html="renderMarkdown(question.answer||'待完善', question.image_layout||{})"/><label>解析</label><div class="question-prose" v-html="renderMarkdown(question.analysis||'原资料未提供', question.image_layout||{})"/></div>
    <template v-if="question.attributes.scoring_criteria"><label>评分标准</label><div class="question-prose" v-html="renderMarkdown(question.attributes.scoring_criteria, question.image_layout||{})"/></template>
  </div>
</template>
