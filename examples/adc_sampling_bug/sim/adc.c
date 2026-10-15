/*
 * SIMULATION FIXTURE - not real firmware.
 * Used only to demonstrate the orchestrator loop: the constants below drive
 * examples/adc_sampling_bug/sim/simulate_log.py, so editing them changes the
 * generated serial log in a reproducible way.
 */

#define PWM_FREQ_HZ          40000   /* center-aligned, 25 us period        */
#define SAMPLE_OFFSET_US     5       /* ADC trigger offset from period start */
#define SETTLING_US          12      /* min settling time after switch edge  */
#define ADC_RMS_LIMIT        5       /* acceptance: adc_rms <= limit         */

/* Trigger the ADC SAMPLE_OFFSET_US after the start of each PWM period. */
void ADC_ConfigureTrigger(void)
{
    /* TODO(agent): the sample point must not fall inside the ringing window */
}
