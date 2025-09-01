import random

import psynet.experiment
from psynet.asset import LocalStorage, OnDemandAsset, S3Storage  # noqa
from psynet.modular_page import (
    AudioPrompt,
    AudioRecordControl,
    ModularPage,
)
from psynet.page import InfoPage, VolumeCalibration
from psynet.timeline import Timeline, CodeBlock, PageMaker, while_loop, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker
from psynet.consent import NoConsent




# Here we define the stimulus set in an analogous way to the static_audio demo,
# except we randomise the start_frequency from a continuous range.
nodes = [
    StaticNode(
        definition={
            "frequency_gradient": frequency_gradient,
        },
    )
    for frequency_gradient in [-100, -50, 0, 50, 100]
]


class CustomTrial(StaticTrial):
    _time_trial = 3
    _time_feedback = 2

    time_estimate = _time_trial + _time_feedback
    wait_for_feedback = True

    def finalize_definition(self, definition, experiment, participant):
        definition["start_frequency"] = random.uniform(-100, 100)
        definition["frequencies"] = [
            definition["start_frequency"] + i * definition["frequency_gradient"]
            for i in range(5)
        ]
        self.add_assets(
            {
                "stimulus": OnDemandAsset(
                    function=synth_stimulus,
                    extension=".wav",
                )
            }
        )
        return definition

    def show_trial(self, experiment, participant):
        return ModularPage(
            "imitation",
            AudioPrompt(
                self.assets["stimulus"],
                "Please imitate the spoken word as closely as possible.",
            ),
            AudioRecordControl(duration=3.0, bot_response_media="example-bier.wav"),
            time_estimate=self._time_trial,
        )

    def show_feedback(self, experiment, participant):
        return ModularPage(
            "feedback_page",
            AudioPrompt(
                self.assets["imitation"],
                "Listen back to your recording. Did you do a good job?",
            ),
            time_estimate=self._time_feedback,
        )

    #def finalize_definition(definition, experiment, participant)
    #    pass


class Exp(psynet.experiment.Experiment):
    label = "Adaptive Testing"
    psynet.experiment.Experiment.max_exp_dir_size_in_mb = 2000   # Prevent error if exceeding the default 256 MB limit.
    consent_page = NoConsent()

    asset_storage = LocalStorage()

    def select_next_item(participant):
        test = participant.var.adaptive_test
        previous_trials = CustomTrial.query.filter_by(participant_id=participant.id).all()


    def evaluate_response(participant):

        def get_response(participant):
            return participant.answer

        test = participant.var.adaptive_test
        test.get_response = get_response
        test.run_test_once()
        # Careful: watch out for PsyNet not updating the participant.var.adaptive_test,
        # because it's an inplace update.
        # This should hopefully work though:
        participant.var.adaptive_test = test



    timeline = Timeline(
        InfoPage(
            """
            In this experiment you will hear some words. Your task will be to repeat
            them back as accurately as possible.
            """,
            time_estimate=5,
        ),
        lambda participant: participant.var.set("stopping_criterion_not_fulfilled", True),
        lambda participant: participant.var.set("stopping_criterion_not_fulfilled", True),
        StaticTrialMaker(
            id_="static_audio_2",
            trial_class=CustomTrial,
            nodes=nodes,
            expected_trials_per_participant=len(nodes),
            target_n_participants=3,
            recruit_mode="n_participants",
        ),
        while_loop(
           label="Adaptive test loop",
            condition=lambda participant: participant.var.stopping_criterion_not_fulfilled,
            logic=join(
                CodeBlock(select_next_item),  # loads the adaptive test, and sets the current_item
                PageMaker(lambda: CustomTrial.cue({
                    "item": participant.var.current_item,
                })),
                CodeBlock(evaluate_response),
            )
        ),
    )
