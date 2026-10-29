<template>
  <ProfileSettings
    v-if="step === 'profile-settings'"
    @updateStep="updateStep"
  />
  <UserEmailSettings
    v-else-if="step === 'user-email-settings'"
    @updateStep="updateStep"
  />
  <PersonalMailboxSettings
    v-else-if="step === 'personal-mailbox-settings'"
    @updateStep="updateStep"
  />
  <PersonalAPISettings
    v-else-if="step === 'personal-api-settings'"
    @updateStep="updateStep"
  />
</template>
<script setup>
import ProfileSettings from './ProfileSettings.vue'
import UserEmailSettings from './UserEmailSettings.vue'
import PersonalMailboxSettings from './PersonalMailboxSettings.vue'
import PersonalAPISettings from './PersonalAPISettings.vue'
import { ref } from 'vue'

const step = ref('profile-settings')

function updateStep(newStep) {
  step.value = newStep
}
</script>
