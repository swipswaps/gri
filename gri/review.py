import datetime
import logging
import os
import re

from gri.console import link

LOG = logging.getLogger(__name__)


class Review:
    """Defines a change-request or pull-request."""

    def __init__(self, data, server):
        self.data = data
        self.server = server
        self.score = 1.0

        LOG.debug(data)

        if "topic" not in data:
            self.topic = ""
        else:
            self.topic = data["topic"]

        self.is_wip = re.compile("^\\[?(WIP|DNM|POC).+$", re.IGNORECASE).match(
            self.subject
        )
        self.url = "{}#/c/{}/".format(self.server.url, self.number)

        self.labels = {}
        for label_name, label_data in data.get("labels", {}).items():
            label = Label(label_name, label_data)
            self.labels[label_name] = label
            if label.abbr == "W":
                self.score += label.value * 20
            if label.abbr == "CR":
                self.score += label.value * 10
            if label.abbr == "V":
                self.score += label.value * 5
                if label.value == 0:
                    self.score -= 100
        if self.starred:
            self.score += 10

        # We just want to keep wip changes in the same are ~0..1 score.
        if self.is_wip:
            self.score /= 100

    def age(self) -> int:
        """Return how many days passed since last update was made."""
        time_now = datetime.datetime.now()
        cr_last_updated = self.data["updated"]
        time_cr_updated = datetime.datetime.strptime(
            cr_last_updated[:-3], "%Y-%m-%d %H:%M:%S.%f"
        )
        return int((time_now - time_cr_updated).days)

    def __repr__(self):
        return str(self.number)

    def __getattr__(self, name):
        if name in self.data:
            return self.data[name]
        if name == "number":
            return self.data["_number"]
        return None

    def short_project(self):
        return re.search("([^/]*)$", self.project).group(0)

    def background(self):
        styles = [
            "normal",
            "low",
            "moderate",
            "considerable",
            "veryhigh",
        ]
        if self.is_wip:
            return styles[0]
        scores = [
            40,
            15,
            10,
            0,
            -10,
        ]
        i = 0
        for i, score in enumerate(scores):
            if self.score > score:
                break
        return styles[i]

    def __str__(self):

        prefix = "%s%s" % (
            "⭐" if self.starred else "  ",
            " " * (8 - len(str(self.number))),
        )

        msg = f"{prefix}[{self.background()}]{link(self.url, self.number)}[/]"

        msg += f" [dim]{self.age():3}[/]"

        msg += f" [{ 'wip' if self.is_wip else 'normal' }]{self.short_project()}[/]"

        if self.branch != "master":
            msg += f" [branch][{self.branch}][/]"

        msg += "[dim]: %s[/]" % (self.subject)

        if self.topic:
            topic_url = "{}#/q/topic:{}+(status:open+OR+status:merged)".format(
                self.server.url, self.topic
            )
            msg += f" {link(topic_url, self.topic)}"

        if not self.mergeable:
            msg += " [veryhigh]cannot-merge[/]"

        for label in self.labels.values():
            if label.value:
                # we print only labels without 0 value
                msg += " %s" % label

        msg += f" [dim]{self.score}[/]"

        return msg

    def is_reviewed(self):
        return self.data["labels"]["Code-Review"]["value"] > 1

    def __lt__(self, other):
        return self.score >= other.score

    def abandon(self, dry=True):
        # shell out here because HTTPS api to abandon can fail
        if self.draft:
            action = "delete"
        else:
            action = "abandon"

        LOG.warning("Performing %s on %s", action, self.number)
        if not dry:
            cmd = (
                f"ssh -p 29418 {self.server.username}"
                f"@{self.server.hostname} gerrit review "
                f"{self.number},1 --{action} --message too_old"
            )
            os.system(cmd)


# pylint: disable=too-few-public-methods
class Label:
    def __init__(self, name, data):
        self.name = name
        self.abbr = re.sub("[^A-Z]", "", name)
        self.value = 0

        if data.get("blocking", False):
            self.value += -2
        if data.get("approved", False):
            self.value += 2
        if data.get("recommended", False):
            self.value += 1
        if data.get("disliked", False):
            self.value += -1
        if data.get("rejected", False):
            self.value += -1
        if data.get("optional", False):
            self.value = 1
        for unknown in set(data.keys()) - set(
            [
                "blocking",
                "approved",
                "recommended",
                "disliked",
                "rejected",
                "value",
                "optional",
            ]
        ):
            LOG.warning("Found unknown label field %s: %s", unknown, data.get(unknown))

    def __repr__(self):
        msg = self.abbr + ":" + str(self.value)
        if self.value < 0:
            color = "red"
        elif self.value == 0:
            color = "yellow"
        elif self.value > 0:
            color = "green"
        return f"[{color}]{msg}[/]"