from app.modules.optimization.domain.actions.factory import RemediationActionFactory

# Import all strategy modules to trigger registration
import app.modules.optimization.domain.actions.aws.ec2 # noqa
import app.modules.optimization.domain.actions.aws.rds # noqa
import app.modules.optimization.domain.actions.aws.volumes # noqa
import app.modules.optimization.domain.actions.aws.storage # noqa
import app.modules.optimization.domain.actions.aws.network # noqa
import app.modules.optimization.domain.actions.aws.analytics # noqa
import app.modules.optimization.domain.actions.azure.vm # noqa
import app.modules.optimization.domain.actions.gcp.compute # noqa
import app.modules.optimization.domain.actions.saas.github # noqa
import app.modules.optimization.domain.actions.license.base # noqa
import app.modules.optimization.domain.actions.platform.base # noqa
import app.modules.optimization.domain.actions.hybrid.base # noqa

__all__ = ["RemediationActionFactory"]
